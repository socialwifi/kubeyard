import logging
import logging.config


def init_logging():
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'simple': {
                'format': '%(asctime)s [%(levelname)s] %(name)s %(message)s',
                'datefmt': '%H:%M:%S',
            },
            'colored': {
                '()': 'colorlog.ColoredFormatter',
                'fmt': '%(asctime)s %(log_color)s[%(levelname)s]%(reset)s %(message)s',
                'datefmt': '%H:%M:%S',
                'log_colors': {
                    'DEBUG':    'cyan',
                    'INFO':     'white',
                    'WARNING':  'yellow',
                    'ERROR':    'red',
                    'CRITICAL': 'red,bold_red',
                },
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': logging.DEBUG,
                'formatter': 'simple',
            },
            'console-colored': {
                'class': 'logging.StreamHandler',
                'level': logging.DEBUG,
                'formatter': 'colored',
            },
        },
        'root': {
            'level': logging.INFO,
            'handlers': ['console']
        },
        'loggers': {
            'sw_cli': {
                'level': logging.INFO,
                'handlers': ['console-colored'],
                'propagate': False,
            },
            'sh.command': {
                'level': logging.WARNING,
            }
        }
    })
