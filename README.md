# Disk Performance Tester

Утилита для тестирования производительности дисков с использованием `fio` с визуализацией результатов.

## Требования

- Python 3.8+
- Установленные пакеты: `matplotlib`, `pandas`, `numpy`
- Утилита `fio` (установится автоматически при первом запуске)

## Установка

1. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

## Основные параметры

Обязательные параметры (должны быть указаны одним из способов):

| Параметр          | Описание                 | Значение по умолчанию |
|-------------------|-------------------------|-----------------------|
| `--ioengine`      | IO engine                | `libaio`              |
| `--direct`        | Direct IO mode           | `1`                   |
| `--buffered`      | Buffered IO mode         | `0`                   |
| `--blocksize`     | Размер блока             | `4k`                  |
| `--iodepth`       | Глубина очереди IO       | `64`                  |

## Дополнительные параметры

Дополнительные параметры, влияющие на тестирование:

| Параметр               | Описание                     | Значение по умолчанию |
|------------------------|------------------------------|----------------------|
| `--runtime`            | Длительность теста в секундах | `300`                |
| `--numjobs`            | Количество параллельных задач | `1`                  |
| `--filename`           | Путь к тестовому файлу       | `/tmp/testfile`      |
| `--file_size`          | Размер тестового файла       | `1G`                 |
| `--base_results_dir`   | Директория для результатов   | `./results`          |
| `--latency_threshold`  | Порог задержки для отметок на графике | `1.0 мс`             |
| `--config`             | Путь к JSON-файлу конфигурации | Нет                  |

## Примеры запуска

### Запуск с параметрами по умолчанию:
```
./fio_test.py
```

### Запуск с явным указанием обязательных параметров:
```
./fio_test.py --ioengine libaio --direct 1 --buffered 0 --blocksize 4k --iodepth 64
```

### Запуск с изменением параметров тестирования:
```
./fio_test.py --runtime 600 --iodepth 32 --latency_threshold 2.0
```

## Формат конфигурационного файла

Пример `fio_config.json`:

```json
{
    "ioengine": "libaio",
    "direct": 1,
    "buffered": 0,
    "blocksize": "4k",
    "iodepth": 64,
    "runtime": 60,
    "numjobs": 1,
    "filename": "/tmp/testfile",
    "file_size": "1G",
    "base_results_dir": "./results",
    "latency_threshold": 1.0,
    "patterns": [
        ["100read_0write", {"rw": "randread", "rwmixread": 100}],
        ["50read_50write", {"rw": "randrw", "rwmixread": 50}],
        ["70read_30write", {"rw": "randrw", "rwmixread": 70}],
        ["0read_100write", {"rw": "randwrite", "rwmixread": 0}]
    ]
}
