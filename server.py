# TODO Переделать логирование
import mimetypes
import os
import socket
import random
from validator import port_validation, check_port_open

DEFAULT_PORT = 80


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
        assert (
            self._socket is not None
        ), "ServerSocket должен быть открыт для получения данных"
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
    response_404 = "<html><h1>404 File Not Found</h1></html>"
    log_format = "{status_code} - {method} {path} {user_agent}"

    def __init__(self, port=80, homedir=os.path.curdir, page404=None):
        """
        Инициализирует сервер

        port    -- порт, на котором разворачивается
        homedir -- домашняя директория
        page404 -- страница, если ресурс не найден
        """
        self.socket = LocaleSocket(port=port)
        self.homedir = os.path.abspath(homedir)

        if page404:
            with open(page404) as f:
                self.response_404 = f.read()

    def log(self, msg: str):
        print(msg)

    def start(self):
        self.socket.open()
        self.log(
            f"Opening socket connection {self.socket.host}:{self.socket.port} in {self.homedir}"
        )
        while True:
            self.serve_request()

    def stop(self):
        self.socket.close()

    def serve_request(self):
        request = self.socket.listen()
        path = request.path
        try:
            body, status_code = self.load_file(path)
        except IsADirectoryError:
            path = os.path.join(path, "index.html")
            body, status_code = self.load_file(path)

        header = self.get_header(status_code, path)
        self.socket.respond((header + body).encode())
        self.log(
            self.log_format.format(
                status_code=status_code,
                method=request.method,
                path=request.path,
                user_agent=request.user_agent,
            )
        )

    def get_header(self, status_code: int, path: str):
        _, file_ext = os.path.splitext(path)
        return "\n".join(
            [
                f"HTTP/1.1 {status_code} {self.STATUSES[status_code]}",
                f"Content-Type: {mimetypes.types_map.get(file_ext, 'application/octet-stream')}",
                "Server: SimplePython Server" "\n\n",
            ]
        )

    def load_file(self, path):
        try:
            with open(os.path.join(self.homedir, path.lstrip("/"))) as f:
                return f.read(), 200
        except FileNotFoundError:
            return self.response_404, 404


def main():
    port_input = input("Введите номер порта для сервера -> ")
    # Тут проверка на то, занят ли порт
    port_flag = port_validation(port_input, check_open=True)

    if not port_flag:

        port_input = DEFAULT_PORT
        # Если порт по-умолчанию уже занят, то перебираем свободные порты
        if not check_port_open(DEFAULT_PORT):
            print(
                f"Порт по умолчанию {DEFAULT_PORT} уже занят! Подбираем рандомный порт.."
            )
            stop_flag = False
            current_port = None
            while not stop_flag:
                current_port = random.randint(49152, 65535)
                print(f"Сгенерировали рандомный порт {current_port}")
                stop_flag = check_port_open(current_port)

            port_input = current_port
        print(f"Выставили порт {port_input} по умолчанию")

    server = WebServer(int(port_input))
    server.start()
    server.stop()


if __name__ == "__main__":
    main()
