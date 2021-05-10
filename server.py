import logging
import os
import random
import socket
from typing import Tuple

from validator import port_validation, check_port_open

DEFAULT_PORT = 80
LOGGER_FILE = "./logs/server.log"
# Настройки логирования
logging.basicConfig(
    format="%(asctime)-15s [%(levelname)s] %(funcName)s: %(message)s",
    handlers=[logging.FileHandler(LOGGER_FILE)],
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
logger.addHandler(stream_handler)


class BrowserRequest:
    """Экземпляр запроса браузера"""

    def __init__(self, data: bytes):
        lines = []
        # Удаляем все пробелы с запроса браузера
        for d in data.decode("utf8", "replace").split("\n"):
            line = d.strip()
            if line:
                lines.append(line)

        self.method, self.path, self.http_version = lines.pop(0).split(" ")
        self.info = {k: v for k, v in (line.split(": ") for line in lines)}

    def __repr__(self) -> str:
        return f"<BrowserRequest {self.method} {self.path} {self.http_version}>"

    def __getattr__(self, name: str):
        try:
            return self.info["-".join([n.capitalize() for n in name.split("_")])]
        except IndexError:
            raise AttributeError(name)


class LocaleSocket:
    """Класс для работы с сокетами"""

    def __init__(self, host="", port=80, buffer_size=1024, max_queued_connections=5):
        self._connection = None
        self._socket = None
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.max_queued_connections = max_queued_connections

    def __repr__(self) -> str:
        status = "closed" if self._socket is None else "open"
        return f"<{status} ServerSocket {self.host}:{self.port}>"

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self):
        assert self._socket is None, "ServerSocket уже открыт"
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._socket.bind((self.host, self.port))
        except Exception:
            self.close()
            raise
        else:
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def close(self):
        assert self._socket is not None, "Данный ServerSocket уже был закрыт"
        if self._connection:
            self._connection.close()
            self._connection = None
        self._socket.close()
        self._socket = None

    def listen(self) -> BrowserRequest:
        assert (self._socket is not None), "ServerSocket должен быть открыт для получения данных"
        self._socket.listen(self.max_queued_connections)
        self._connection, _ = self._socket.accept()
        data = self._connection.recv(self.buffer_size)
        return BrowserRequest(data)

    def respond(self, data: bytes):
        assert self._socket is not None, "ServerSocket должен быть открыт для ответа"
        self._connection.send(data)
        self._connection.close()


class WebServer:
    """Класс сервера"""

    STATUSES = {
        200: "Ok",
        404: "File not found",
    }

    def __init__(self, port: int = 80, homedir: str = "html/"):
        """
        Инициализирует сервер

        port    -- порт, на котором разворачивается
        homedir -- домашняя директория
        """
        self.socket = LocaleSocket(port=port)
        self.homedir = os.path.abspath(homedir)

    def start(self):
        """Запуск web-сервера"""
        self.socket.open()
        logger.info(f"Запустили web-сервер на порту {self.socket.host}:{self.socket.port}, директория {self.homedir}")
        while True:
            self.new_client_request()

    def stop(self):
        """Приостановка работы web-сервера"""
        self.socket.close()

    def router(self, path: str) -> Tuple[str, int]:
        """Роутер для ассоциации между путями и файлами"""
        router_dict = {
            "/": "index.html",
            "/index.html": "index.html",
            "/index": "index.html",
        }

        # Если такой маппинг действительно существует
        if path in router_dict:
            path_str = os.path.join(self.homedir, router_dict[path])
            with open(path_str) as f:
                return f.read(), 200

        # Если ничего подобного нет, то 404
        else:
            with open(os.path.join(self.homedir, "404.html")) as f:
                return f.read(), 404

    def new_client_request(self):
        """"Обработка запроса клиента"""
        cli_request = self.socket.listen()
        path = cli_request.path
        # Получаем результат существования файла от роутера
        body, status_code = self.router(path)
        header = self.get_header(status_code)
        self.socket.respond((header + body).encode())
        logger.info(f"{status_code} - {cli_request.method} {path} {cli_request.user_agent}")

    def get_header(self, status_code: int):
        """Получает заголовок для ответа сервера"""
        return "\n".join(
            [
                f"HTTP/1.1 {status_code} {self.STATUSES[status_code]}",
                "Content-Type: text/html;charset=UTF-8",
                "Server: MyServer" "\n\n",
            ]
        )


def main():
    port_input = input("Введите номер порта для сервера -> ")
    # Тут проверка на то, занят ли порт
    port_flag = port_validation(port_input, check_open=True)

    if not port_flag:

        port_input = DEFAULT_PORT
        # Если порт по-умолчанию уже занят, то перебираем свободные порты
        if not check_port_open(DEFAULT_PORT):
            logger.info(
                f"Порт по умолчанию {DEFAULT_PORT} уже занят! Подбираем рандомный порт.."
            )
            stop_flag = False
            current_port = None
            while not stop_flag:
                current_port = random.randint(49152, 65535)
                logger.info(f"Сгенерировали рандомный порт {current_port}")
                stop_flag = check_port_open(current_port)

            port_input = current_port
        logger.info(f"Выставили порт {port_input} по умолчанию")

    web_server = WebServer(port=int(port_input))
    web_server.start()
    web_server.stop()


if __name__ == "__main__":
    main()
