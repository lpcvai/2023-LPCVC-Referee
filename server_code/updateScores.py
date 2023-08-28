import os
import requests
import time
import sys

my_env = os.environ.copy()
SITE_URL = my_env.get('LPCVC_SITE_URL', 'https://lpcv.ai')

def report_score(submission, output):
    """
    Tell the server to store the average result into the database
    """
    print("INFO: " + submission + " has been scored!\n\n\n\n==================\n")
    time.sleep(0.2)
    if SITE_URL:
        requests.get(SITE_URL + "/organizers/segmentation23/grade/%s/%s" % (submission,output,), verify=False)
        print(SITE_URL + "/organizers/segmentation23/grade/%s/%s" % (submission,output,))

if __name__ == "__main__":
    submission = sys.argv[1]
    output = sys.argv[2]
    report_score(submission,output)
