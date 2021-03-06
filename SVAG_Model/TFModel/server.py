import uuid
import json
import platform
import time
import os
import logging
import sys
from thread import TaskManager
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

# daemonize process is not supported on Windows
if platform.system() != "Windows":
    import daemon
    import daemon.pidfile
    import lockfile

PORT = 46176
THREAD_NUM = 1
LOCAL_PATH = os.getcwd()
SERVER_LOG = 'server.log'
TASK_MANAGER_LOG = 'taskmanager.log'
LOG_DIR = 'log'
PID_FILE = 'TFModel_server.pid'
SERVER_OUTPUT_LOG = 'server_outputs.log'
SERVER_LOGGER = logging.getLogger('main_server')

# Process HTTP Requests
class SelfHTTPHandler(BaseHTTPRequestHandler):
    def _parse_post_date(self, post_data):
        """
        parse post data to dict, extract important information
        :param post_data: post data from POST Request
        :return: parsed dict
        """
        result = {}
        post_data = parse_qs(post_data)
        # the values of post_data[key_name] is a list of values with key_name
        result['userId'] = post_data.get('userId', [''])[0]
        result['projectId'] = post_data.get('projectId', [''])[0]
        result['projectDir'] = post_data.get('projectDir', [''])[0]
        result['trainType'] = post_data.get('trainType', [''])[0]
        result['taskId'] = str(uuid.uuid1())
        result['state'] = 'initialize'
        result['progress'] = 0
        result['thread'] = ''
        return result

    def _set_headers(self):
        """
        set the header of return HTTP message
        :return:
        """
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def do_GET(self):
        """
        process HTTP GET Request
        :return:
        """

        server_logger = logging.getLogger('main_server')
        d = {'clientip': self.client_address[0]}
        server_logger.info("recv GET request", extra=d)

        # extract task id
        parsed_path = urlparse(self.path)
        parsed_path = parse_qs(parsed_path.query)
        task_id = parsed_path.get('taskId', ['no taskId in query'])[0]
        info = TaskManager().get_task_info(task_id)
        # invalid task id
        if len(info) == 0:
            info['error'] = 'cannot find task info'
        info['taskId'] = task_id
        self._set_headers()
        # return task info
        self.wfile.write(json.dumps(info).encode())

    def do_POST(self):
        """
        process HTTP POST Request
        :return:
        """

        server_logger = logging.getLogger('main_server')
        d = {'clientip': self.client_address[0]}
        server_logger.info("recv POST request", extra=d)

        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        result = self._parse_post_date(post_data.decode())
        TaskManager().add_job(result)
        server_logger.info("initialize task id, added to tasks pool", extra=d)
        self._set_headers()
        self.wfile.write(json.dumps(result).encode())


def initialize_logger():
    # Step 1. create or open server log file and record server start time
    try:
        with open(os.path.join(LOCAL_PATH, LOG_DIR, SERVER_LOG), 'a+') as file:
            file.write("*******************start server at {}*******************\n".format(
                time.asctime(time.localtime(time.time()))))
    except EnvironmentError as e:
        print("[initialize_server_logger]error opening server log file: %s" % e, file=sys.stdout)
        return False, None, None

    # Step 2. initialize and config server logger with name 'main_server'
    server_logger = logging.getLogger('main_server')
    server_logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(os.path.join(LOCAL_PATH, LOG_DIR, SERVER_LOG))
    fh.setLevel(logging.INFO)
    server_formatter = logging.Formatter('%(asctime)s - %(clientip)s - %(message)s')
    fh.setFormatter(server_formatter)
    server_logger.addHandler(fh)

    # Step 3. initialize and config task logger
    task_logger = logging.getLogger('task_manager')
    task_logger.setLevel(logging.DEBUG)
    th = logging.FileHandler(os.path.join(LOCAL_PATH, LOG_DIR, TASK_MANAGER_LOG))
    th.setLevel(logging.INFO)
    task_formatter = logging.Formatter('%(asctime)s - %(threadNmae)s - %(message)s')
    th.setFormatter(task_formatter)
    task_logger.addHandler(th)

    return True, fh, th


def server_run(server_class=HTTPServer, handler_class=SelfHTTPHandler, port=80):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print("[server run]now serving at port: {}".format(port))
    httpd.serve_forever()


def main():
    # create log dir if is not existed
    try:
        if not os.path.exists(os.path.join(LOCAL_PATH, LOG_DIR)):
            os.mkdir(os.path.join(LOCAL_PATH, LOG_DIR))
    except EnvironmentError as e:
        print("[server start]error creating log dir in local path: %s" % e)
        return -1

    # intialize server logger
    success_intialize, server_log_file, task_log_file = initialize_logger()
    if not success_intialize:
        print("[server initialize]error initializing server logger", file=sys.stdout)
        return
    print("[server initialize]initialize logger.................Success", file=sys.stdout)

    # initialize task threading pool(Singleton)
    _ = TaskManager(THREAD_NUM)
    print("[server initialize]initialize Task Manager...........Success", file=sys.stdout)
    
    # daemonize process is not supported on Windows
    print("[server start]start server...")
    if platform.system() == "Windows":
        # start running server, listening to PORT
        server_run(port=PORT)
    else:
        try:
            with daemon.DaemonContext(pidfile=daemon.pidfile.PIDLockFile(os.path.join(LOCAL_PATH, PID_FILE)),
                                      files_preserve= [server_log_file.stream,
                                                       task_log_file.stream]
                                      ):
                server_run(port=PORT)
        except Exception as e:
            print("[server start]error starting server: %s" % e, file=sys.stdout)
            return -1
    


if __name__ == '__main__':
   main()
