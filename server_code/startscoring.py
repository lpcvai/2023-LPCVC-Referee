import os
import getpass
import time
import logging
import subprocess
import re
import sys
import psutil
from updateScores import report_score
from dotenv import load_dotenv
#To run this in the background you can use nohup python3 /home/lpcv-server/referee/source_code/server_code/startscoring.py > /dev/null 2>&1 &
#To stop this script you can kill it by finding process id using ps aux | grep -v grep | grep 'startscoring.py' --- and then kill it with sudo kill ProcessID
#To make sure this script is running on boot of the server you can put it in as a cron job with the configureCron.yml and delete it with the delete
#Just run ansible-playbook configureCron.yml
current_dir = os.path.dirname(os.path.abspath(__file__))
environment_dir=current_dir+"/../referee.environment"
load_dotenv(dotenv_path=environment_dir)

# Define the local directory to monitor
LOCAL_DIR = os.getenv('LPCVC_QUEUE_DIR')
LOCAL_SCORED_DIR= os.getenv('LPCVC_SCORED_DIR')
LOCAL_FAILED_DIR= os.getenv('LPCVC_FAILED_DIR')
LOCAL_TIMED_OUT_DIR= os.getenv('LPCVC_TIMED_OUT_DIR')


# Define the remote directory to transfer files to
REMOTE_DEVICE = os.getenv('LPCVC_NANO_USER')
REMOTE_DIR = os.getenv('LPCVC_NANO_TEST_DIR') #/processManager/queue'

# Define the delay between transfer attempts (in seconds)
TRANSFER_DELAY = 60

# Get the directory of this script and create the log file path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.getenv('LOG_FILE')

# Configure logging
def configure_logging():
    logging_file = open(LOG_FILE, 'a')
    logging.basicConfig(stream=logging_file, level=logging.INFO, format='%(asctime)s - %(message)s')




def check_if_process_running(process_name):
    '''
    Check if there is any running process that contains the given name processName,
    excluding the current process and its parent (shell) process.
    '''
    current_process_id = os.getpid()
    current_process = psutil.Process(current_process_id)
    parent_process_id = current_process.ppid()

    count = 0
    for proc in psutil.process_iter():
        try:
            # Check if process name contains the given name string and it is not the current process or its parent
            if (process_name in [arg.rsplit('/')[-1] for arg in proc.cmdline()] and
                proc.pid != current_process_id and
                proc.pid != parent_process_id):
                count += 1
                if count > 0:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

#Make sure file is fully transferred
def is_file_done_transferring(filepath, check_interval=1, stable_duration=1):
    prev_size = -1
    stable_start_time = None

    while True:
        current_size = os.path.getsize(filepath)

        if current_size == prev_size:
            if stable_start_time is None:
                stable_start_time = time.time()
            elif time.time() - stable_start_time >= stable_duration:
                return True
        else:
            stable_start_time = None

        prev_size = current_size
        time.sleep(check_interval)
def scp_transfer(local_file_path, remote_file_path):
    scp_command = 'scp {} {}:{}'.format(local_file_path, REMOTE_DEVICE, remote_file_path)
    subprocess.run(scp_command, shell=True, check=True)
    logging.info('Transferred file %s to remote directory %s', local_file_path, remote_file_path)

def run_evaluation_script(filename):
    ssh_command = 'ssh {} "export OPENBLAS_CORETYPE=ARMV8 && cd {} && ./evaluation.bash {} "'.format(REMOTE_DEVICE, REMOTE_DIR, filename)
    exit_code = subprocess.call(ssh_command, shell=True)
    return exit_code
def move_local_file(src, dest):
    os.rename(src, dest)

def download_scored_file(remote_file_path, local_file_path):
    scp_download_command = 'scp {}:{} {}'.format(REMOTE_DEVICE, remote_file_path, local_file_path)
    subprocess.run(scp_download_command, shell=True, check=True)

def remove_remote_file(remote_file_path):
    remove_remote_file_command = 'ssh {} "rm {}"'.format(REMOTE_DEVICE, remote_file_path)
    subprocess.run(remove_remote_file_command, shell=True, check=True)

def process_file(filename):
    if is_file_done_transferring(os.path.join(LOCAL_DIR, filename)):
        transfer_success = False
        run_success = False
        get_file = False
        while not transfer_success or not run_success or not get_file:
            try:
                if not transfer_success:
                    scp_transfer(os.path.join(LOCAL_DIR, filename), os.path.join(REMOTE_DIR, filename))
                    transfer_success = True
                else:
                    if not run_success:
                        time.sleep(1)
                        exit_code = run_evaluation_script(filename)
                        local_folder = None
                        if exit_code == 0:  # Scored
                            local_folder = LOCAL_SCORED_DIR
                            updateFolder = 'scored'
                            logging.info('File %s scored', filename)
                            run_success = True
                        elif exit_code == 2:  # timedout
                            local_folder = LOCAL_TIMED_OUT_DIR
                            updateFolder = 'timedOut'
                            logging.error('File %s timed out', filename)
                            run_success = True
                        else:  # Failed
                            local_folder = LOCAL_FAILED_DIR
                            updateFolder = 'failed'
                            logging.error('File %s failed', filename)

                    scored_filename = os.path.splitext(filename)[0] + '.json'
                    download_scored_file(os.path.join(REMOTE_DIR, 'output', scored_filename), os.path.join(local_folder, scored_filename))
                    logging.info('downloaded %s scored file', filename)
                    remove_remote_file(os.path.join(REMOTE_DIR, filename))
                    logging.info('removed %s from remote', filename)
                    move_local_file(os.path.join(LOCAL_DIR, filename), os.path.join(local_folder, filename))
                    logging.info('moved scored file%s', filename)
                    #report_score(os.path.splitext(filename)[0], updateFolder)
                    logging.info('updated %s score', os.path.splitext(filename)[0])
                    run_success = True
                    get_file = True

            except subprocess.CalledProcessError as e:
                logging.error('Failed to transfer file %s to remote directory %s', filename, REMOTE_DIR)
                time.sleep(TRANSFER_DELAY)

def main_loop():
    print("Monitoring Directory")
    while True:
        files = os.listdir(LOCAL_DIR)
        files.sort(key=lambda x: os.path.getctime(os.path.join(LOCAL_DIR, x)))
        for filename in files:
            if os.path.isfile(os.path.join(LOCAL_DIR, filename)):
                process_file(filename)
        time.sleep(150)

if __name__ == "__main__":
    script_name = os.path.basename(__file__)
    if check_if_process_running(script_name):
        print("Script is already running.")
        sys.exit(1)
    configure_logging()
    main_loop()