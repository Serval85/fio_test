#!/usr/bin/env python3
import json
import os
import subprocess
import time
import argparse
from datetime import datetime
from typing import Dict, Tuple, Optional, List

import matplotlib.pyplot as plt
import pandas as pd


class RWTest:
    def __init__(self, config_file: Optional[str] = None, cli_args: Optional[Dict] = None):
        """Инициализация класса для тестирования производительности диска.

        Args:
            config_file (str, optional): Путь к JSON-файлу конфигурации.
            cli_args (dict, optional): Аргументы командной строки.
        """
        # Значения по умолчанию для обязательных параметров
        self.required_defaults = {
            "ioengine": "libaio",
            "direct": 1,
            "buffered": 0,
            "blocksize": "4k",
            "iodepth": 64
        }

        # Остальные значения по умолчанию
        self.optional_defaults = {
            "runtime": 300,
            "numjobs": 1,
            "filename": "/tmp/testfile",
            "file_size": "1G",
            "base_results_dir": "./results",
            "latency_threshold": 1.0,  # Порог задержки в мс
            "patterns": [
                ["100read_0write", {"rw": "randread", "rwmixread": 100}],
                ["50read_50write", {"rw": "randrw", "rwmixread": 50}],
                ["70read_30write", {"rw": "randrw", "rwmixread": 70}],
                ["0read_100write", {"rw": "randwrite", "rwmixread": 0}]
            ]
        }

        # Загружаем конфиг из файла, если он указан и существует
        file_config = {}
        if config_file and os.path.exists(config_file):
            with open(config_file) as f:
                file_config = json.load(f)

        # Объединяем конфиги с учетом приоритетов: cli_args > file_config > default_config
        self.config = {**self.required_defaults, **self.optional_defaults, **file_config}
        if cli_args:
            self.config.update(cli_args)

        # Проверяем, что обязательные параметры присутствуют (могут быть переопределены)
        for param in self.required_defaults.keys():
            if param not in self.config:
                raise ValueError(f"Обязательный параметр {param} не указан")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.results_dir = os.path.join(
            self.config["base_results_dir"], f"run_{timestamp}")
        os.makedirs(self.results_dir, exist_ok=True)

    def setup_environment(self):
        """Подготовка тестового окружения: удаление старого тестового файла и проверка наличия fio."""
        if os.path.exists(self.config["filename"]):
            os.remove(self.config["filename"])

        try:
            subprocess.run(["fio", "--version"], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Установка fio...")
            subprocess.run(["sudo", "apt", "update"], check=True)
            subprocess.run(["sudo", "apt", "install", "-y", "fio"], check=True)

    def run_fio_test(self, pattern: Tuple[str, Dict]) -> str:
        """Запуск теста fio с заданным паттерном.

        Args:
            pattern (Tuple[str, Dict]): Кортеж с именем паттерна и параметрами теста.

        Returns:
            str: Путь к файлу с результатами.
        """
        name, params = pattern
        output_file = f"{self.results_dir}/result_{name}.json"
        base_name = output_file.replace('.json', '')

        cmd = [
            "fio",
            "--name=test",
            f"--ioengine={self.config['ioengine']}",
            f"--direct={self.config['direct']}",
            f"--buffered={self.config['buffered']}",
            f"--bs={self.config['blocksize']}",
            f"--iodepth={self.config['iodepth']}",
            f"--filename={self.config['filename']}",
            f"--size={self.config['file_size']}",
            f"--rw={params['rw']}",
            f"--rwmixread={params['rwmixread']}",
            f"--runtime={self.config['runtime']}",
            f"--numjobs={self.config['numjobs']}",
            "--time_based",
            "--group_reporting",
            "--norandommap",
            "--output-format=json",
            f"--output={output_file}",
            f"--write_iops_log={base_name}",
            f"--write_lat_log={base_name}",
            "--log_avg_msec=1000"
        ]

        print(f"\nЗапуск теста {name}:")
        start_time = time.time()

        try:
            with subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True) as proc:
                while proc.poll() is None:
                    elapsed = int(time.time() - start_time)
                    total = self.config["runtime"]
                    print(f"\rПрогресс: {elapsed}/{total} сек", end="", flush=True)
                    time.sleep(1)

                if proc.returncode != 0:
                    raise subprocess.CalledProcessError(
                        proc.returncode, cmd, proc.stdout.read(), proc.stderr.read())

        except KeyboardInterrupt:
            proc.terminate()
            raise

        print(f"\nТест {name} завершен за {time.time() - start_time:.1f}с")
        return output_file

    def parse_results(self, json_file: str, pattern_name: str) -> Dict:
        """Анализ результатов теста из JSON-файла.

        Args:
            json_file (str): Путь к JSON-файлу с результатами теста.
            pattern_name (str): Имя паттерна теста.

        Returns:
            Dict: Словарь с извлеченными результатами теста.
        """
        with open(json_file) as f:
            data = json.load(f)

        job = data["jobs"][0]
        results = {
            "pattern": pattern_name,
            "read_iops": job["read"]["iops"],
            "read_bw": job["read"]["bw"],
            "read_lat_avg": None,
            "read_lat_max": None
        }

        # Обработка задержек чтения (конвертация ns → ms)
        if "lat" in job["read"]:
            lat = job["read"]["lat"]
            if "mean" in lat:
                results["read_lat_avg"] = lat["mean"] / 1_000_000  # ns → ms
            if "max" in lat:
                results["read_lat_max"] = lat["max"] / 1_000_000  # ns → ms

        # Обработка операций записи
        if "write" in job:
            results.update({
                "write_iops": job["write"]["iops"],
                "write_bw": job["write"]["bw"],
                "write_lat_avg": None,
                "write_lat_max": None
            })

            # Обработка задержек записи (конвертация ns → ms)
            if "lat" in job["write"]:
                lat = job["write"]["lat"]
                if "mean" in lat:
                    results["write_lat_avg"] = lat["mean"] / 1_000_000
                if "max" in lat:
                    results["write_lat_max"] = lat["max"] / 1_000_000

        return results

    def plot_iops(self, pattern_name: str):
        """Построение графика IOPS с отметками о высокой задержке.

        Args:
            pattern_name (str): Имя паттерна теста для построения графика.
        """
        base_file = f"{self.results_dir}/result_{pattern_name}"
        threshold = self.config["latency_threshold"]

        try:
            # Загрузка данных IOPS
            iops_data = pd.read_csv(f"{base_file}_iops.1.log",
                                    header=None,
                                    names=['time_ms', 'iops', 'r', 'w', 'lat'])

            plt.figure(figsize=(14, 7))

            # Разделение данных IOPS
            read_iops = iops_data[iops_data['r'] == 0]
            write_iops = iops_data[iops_data['r'] == 1]

            # Построение графиков IOPS
            plt.plot(read_iops['time_ms'] / 1_000, read_iops['iops'],
                     label='Read IOPS', color='blue')

            if not write_iops.empty:
                plt.plot(write_iops['time_ms'] / 1_000, write_iops['iops'],
                         label='Write IOPS', color='red')

            # Обработка данных о задержке (µs → ms)
            try:
                lat_data = pd.read_csv(f"{base_file}_lat.1.log",
                                       header=None,
                                       names=['time_ms', 'lat', 'r', 'w', 'l'])

                # Конвертация µs → ms
                lat_data['lat_ms'] = lat_data['lat'] / 1_000_000
                high_lat = lat_data[lat_data['lat_ms'] > threshold]

                if not high_lat.empty:
                    for _, row in high_lat.iterrows():
                        plt.axvline(x=row['time_ms'] / 1_000, color='orange',
                                    linestyle='--', alpha=0.3, linewidth=1)

                    plt.axvline(x=0, color='orange', linestyle='--',
                                label=f'Latency > {threshold}ms', alpha=0.3)
            except FileNotFoundError:
                print(f"  Предупреждение: Файл с данными о задержке не найден")
            except Exception as e:
                print(f"  Ошибка обработки данных о задержке: {str(e)}")

            plt.title(f'IOPS over Time: {pattern_name}\n(Latency threshold: {threshold}ms)')
            plt.xlabel('Time (s)')
            plt.ylabel('IOPS')
            plt.grid(True)
            plt.legend()

            plot_file = f"{self.results_dir}/iops_{pattern_name}.png"
            plt.savefig(plot_file, dpi=150, bbox_inches='tight')
            plt.close()
            print(f"  График сохранен в {plot_file}")

        except Exception as e:
            print(f"  Ошибка при построении графика: {str(e)}")

    def run(self):
        """Основной метод для запуска всех тестов и обработки результатов."""
        print("=== Тестирование производительности диска ===")
        print("Конфигурация:")
        for key, value in self.config.items():
            if key != "patterns":
                print(f"  {key}: {value}")

        self.setup_environment()

        for pattern in self.config["patterns"]:
            name = pattern[0]
            try:
                print(f"\n=== Запуск теста {name} ===")
                result_file = self.run_fio_test(pattern)
                results = self.parse_results(result_file, name)
                self.plot_iops(name)

                # Вывод результатов
                print("\nРезультаты:")
                print(f"  Read IOPS: {results['read_iops']:.0f}")
                if results['read_lat_avg'] is not None:
                    print(f"  Read Avg Latency: {results['read_lat_avg']:.2f} ms")
                    print(f"  Read Max Latency: {results['read_lat_max']:.2f} ms")

                if 'write_iops' in results:
                    print(f"\n  Write IOPS: {results['write_iops']:.0f}")
                    if results['write_lat_avg'] is not None:
                        print(f"  Write Avg Latency: {results['write_lat_avg']:.2f} ms")
                        print(f"  Write Max Latency: {results['write_lat_max']:.2f} ms")

            except Exception as e:
                print(f"Ошибка в тесте {name}: {str(e)}")
                continue

        print("\n=== Тестирование завершено ===")
        print(f"Все результаты сохранены в {self.results_dir}")


def parse_args():
    """Парсинг аргументов командной строки.

    Returns:
        argparse.Namespace: Объект с разобранными аргументами командной строки.
    """
    parser = argparse.ArgumentParser(description='Disk performance tester')

    # Обязательные параметры (могут быть переопределены)
    parser.add_argument('--ioengine', help='IO engine to use (default: libaio)')
    parser.add_argument('--direct', type=int, help='Direct IO mode (default: 1)')
    parser.add_argument('--buffered', type=int, help='Buffered IO mode (default: 0)')
    parser.add_argument('--blocksize', help='Block size for IO operations (default: 4k)')
    parser.add_argument('--iodepth', type=int, help='IO depth (default: 64)')

    # Дополнительные параметры
    parser.add_argument('--runtime', type=int, help='Test duration in seconds (default: 300)')
    parser.add_argument('--numjobs', type=int, help='Number of jobs (default: 1)')
    parser.add_argument('--filename', help='Test file path (default: /tmp/testfile)')
    parser.add_argument('--file_size', help='Test file size (default: 1G)')
    parser.add_argument('--base_results_dir', help='Results directory (default: ./results)')
    parser.add_argument('--latency_threshold', type=float,
                        help='Latency threshold in ms for marking on graphs (default: 1.0)')
    parser.add_argument('--config', help='Path to config file')

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Преобразуем аргументы в словарь (только указанные аргументы)
    cli_args = {}
    if args.ioengine is not None:
        cli_args["ioengine"] = args.ioengine
    if args.direct is not None:
        cli_args["direct"] = args.direct
    if args.buffered is not None:
        cli_args["buffered"] = args.buffered
    if args.blocksize is not None:
        cli_args["blocksize"] = args.blocksize
    if args.iodepth is not None:
        cli_args["iodepth"] = args.iodepth

    # Добавляем необязательные аргументы
    optional_args = {
        "runtime": args.runtime,
        "numjobs": args.numjobs,
        "filename": args.filename,
        "file_size": args.file_size,
        "base_results_dir": args.base_results_dir,
        "latency_threshold": args.latency_threshold
    }

    for key, value in optional_args.items():
        if value is not None:
            cli_args[key] = value

    tester = RWTest(config_file=args.config, cli_args=cli_args)
    tester.run()