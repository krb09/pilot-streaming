#!/usr/bin/env python

import textwrap
import re
import os
import pdb
import logging
import subprocess
import math
import uuid
from urllib.parse import urlparse
import tempfile
import time
import signal 


logging.basicConfig(datefmt='%m/%d/%Y %I:%M:%S %p',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(name='pilot-streaming')

# logger.basicConfig(datefmt='%m/%d/%Y %I:%M:%S %p',
#           format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger.setLevel(logging.DEBUG)


#import saga


class Service(object):
    """ Plugin for SlURM    """

    def __init__(self, resource_url):
        """Constructor"""
        self.resource_url = resource_url

    def create_job(self, job_description):
        j = Job(job_description, self.resource_url)
        return j

    def __del__(self):
        pass


class Job(object):
    """Constructor"""

    def __init__(self, job_description, resource_url):
        
        self.job_description = job_description
        self.command = self.job_description["executable"]
        if "arguments" in self.job_description:
            args =  self.job_description["arguments"]
            if isinstance(self.job_description["arguments"], list):
                args =  " ".join(self.job_description["arguments"])
        
        self.command = (("%s %s") % (self.job_description["executable"], args))
        logging.debug("Command: %s"%self.command)
            
        # Pilot-Streaming Internal UID
        self.job_uuid = str(uuid.uuid1())
        self.job_uuid_short =  "ps-%s"%self.job_uuid[:5]
        
        # Job ID at local resource manager (SLURM)
        self.job_id = ""
        
        # slurm+ssh:// URL for local resource manager endpoint for submission
        self.resource_url = resource_url
        
        o = urlparse(self.resource_url)
        self.target_host = o.netloc
        
        logger.debug("Pilot-Streaming SLURM: Parsing job description: %s"%str(job_description))
        
        self.pilot_compute_description = {}
        if 'queue' in job_description: 
            self.pilot_compute_description['queue'] = job_description['queue']
        
        logging.debug("Queue: %s"%self.pilot_compute_description['queue'])
        
        if 'project' in job_description: 
            self.pilot_compute_description['project'] = job_description['project']

        if 'reservation' in job_description:
            self.pilot_compute_description['reservation'] = job_description['reservation']
        
        self.pilot_compute_description['working_directory'] = os.getcwd()
        if 'working_directory' in job_description: 
            self.pilot_compute_description['working_directory'] = job_description['working_directory']
        
        self.pilot_compute_description['output'] = os.path.join(self.pilot_compute_description['working_directory'], "ps-%s.stdout"%self.job_uuid_short)
        if 'output' in job_description: 
            self.pilot_compute_description['output'] = job_description['output']
        
        self.pilot_compute_description['error'] = os.path.join(self.pilot_compute_description['working_directory'], "ps-%s.stderr"%self.job_uuid_short)
        if 'error' in job_description: 
            self.pilot_compute_description['error'] = job_description['error']
        
        if 'walltime' in job_description: 
            self.pilot_compute_description['walltime'] = job_description['walltime']

        
        #if 'number_cores' in job_description: 
        #    self.pilot_compute_description['number_cores'] = job_description['number_cores']

        self.pilot_compute_description['cores_per_node']=48
        if 'cores_per_node' in job_description: 
            self.pilot_compute_description['cores_per_node'] = int(job_description['cores_per_node'])
     
        self.pilot_compute_description['number_of_nodes'] = 1
        if 'number_of_nodes' in job_description: 
            self.pilot_compute_description['number_of_nodes'] = int(job_description['number_of_nodes'])
            
        self.pilot_compute_description['number_cores']=self.pilot_compute_description['cores_per_node'] * self.pilot_compute_description['number_of_nodes']

        self.working_directory = self.pilot_compute_description["working_directory"]
        ### convert walltime in minutes to SLURM representation of time ###
        walltime_slurm = "01:00:00"
        if "walltime" in self.pilot_compute_description:
            hrs = math.floor(int(self.pilot_compute_description["walltime"]) / 60)
            minu = int(self.pilot_compute_description["walltime"]) % 60
            walltime_slurm = "" + str(hrs) + ":" + str(minu) + ":00"
        self.pilot_compute_description["walltime_slurm"]=walltime_slurm

       
    def run(self):
        o = urlparse(self.resource_url)
        target_host = o.netloc
        start_command=("ssh %s "%target_host)
        tmpf_name = ""
        logger.debug("Submit pilot job to: " + str(self.resource_url))
        logger.debug("Type Job ID"+str(self.job_uuid_short))
        try:
            fd, tmpf_name = tempfile.mkstemp()
            print(tmpf_name)
            with os.fdopen(fd, 'w') as tmp:
                tmp.write("#!/bin/bash\n")
                tmp.write("#SBATCH -n %s\n"%str(self.pilot_compute_description["number_cores"]))
                tmp.write("#SBATCH -N %s\n"%str(self.pilot_compute_description["number_of_nodes"]))
                tmp.write("#SBATCH -J %s\n"%self.job_uuid_short)
                tmp.write("#SBATCH -t %s\n"%str(self.pilot_compute_description["walltime_slurm"]))
                tmp.write("\n")
                tmp.write("#SBATCH -A %s\n"%str(self.pilot_compute_description["project"]))
                tmp.write("\n")
                if self.pilot_compute_description["reservation"] is not None:
                    tmp.write("#SBATCH --reservation  %s\n"%str(self.pilot_compute_description["reservation"]))
                tmp.write("\n")
                tmp.write("#SBATCH -o %s\n"%self.pilot_compute_description["output"])
                tmp.write("#SBATCH -e %s\n"%self.pilot_compute_description["error"])
                tmp.write("#SBATCH -p %s\n"%self.pilot_compute_description["queue"])
                tmp.write("cd %s\n"%self.pilot_compute_description["working_directory"])
                tmp.write("%s\n"%self.command)
                tmp.flush()
                start_command = ("scp %s %s:~/"%(tmpf_name, target_host))
                status = subprocess.call(start_command, shell=True)
        finally:
            pass
            #os.remove(tmpf)

        start_command = ("ssh %s "%target_host)
        start_command = start_command + ("sbatch  %s"%os.path.basename(tmpf_name))
        print(("Submission of Job Command: %s"%start_command))
        outstr = subprocess.check_output(start_command, 
                                         stderr=subprocess.STDOUT,
                                         shell=True).decode("utf-8") 
       
        
        
        start_command = ("ssh %s "%target_host)
        start_command = start_command + ("rm %s"%os.path.basename(tmpf_name))
        print(("Cleanup: %s"%start_command))
        status = subprocess.call(start_command, shell=True)
        logger.debug("Pilot-Streaming SLURM: SSH run job finished")
        logger.debug("Output - \n" + str(outstr))
        self.job_id=self.get_local_job_id(outstr)
        if self.job_id == None or self.job_id == "":
            raise Exception("Pilot-Streaming Submission via slurm+ssh:// failed")
        
    def get_id(self):
        return self.job_id

    def get_state(self):
        start_command=("%s %s %s"%("squeue", "-j", self.job_id ))
        for i in range(3):
            try:
                output = subprocess.check_output(start_command, stderr=subprocess.STDOUT, shell=True).decode("utf-8") 
                logging.debug("Query State: %s Output: %s"%(start_command, output))        
                #signal.signal(signal.SIGCHLD, signal.SIG_IGN) 
                status = self.get_job_status(output)
                return status
            except:
                logging.debug("Error check for Job Status. Backoff polling")        
                time.sleep(10)
        

    def cancel(self):
        logger.debug("Cancel SLURM job")
        start_command=("%s %s"%("scancel", self.job_id ))
        output = subprocess.check_output(start_command, shell=True).decode("utf-8") 
        logging.debug("Cancel SLURM job: %s Output: %s"%(start_command, output))        
        return self.get_job_status(output)
        
        
    def get_local_job_id(self, output_string):
        match=re.search("(?<=batch\\ job\\ )[0-9]*", str(output_string), re.S)
        if match:
            self.job_id=match.group(0)
            logger.debug("Found SLURM Job ID: %s"%self.job_id)
            return self.job_id
        
    def get_job_status(self, output_string):
        state = "Unknown"
        try:
            state = output_string.split("\n")[-2].split()[4]
        except: 
            logging.debug("No job with ID %s found"%self.job_id)
        if state.upper() == "R":
            state = "Running"
        elif state.upper() == "CD" or state.upper() == "CF" or state.upper() == "CG":
            state = "Done"
        elif state.upper() == "PD":
            state = "Queue"
        else:
            state = "Unknown" 
        return state


if __name__ == "__main__":
    slurm_service = Service("slurm+ssh://login1.wrangler.tacc.utexas.edu")

    jd ={
        "executable":"/bin/date",
        "resource":"slurm://localhost",
        "working_directory": os.path.join('/work/01131/tg804093/wrangler/', "work"),
        "number_cores": 48,
        "number_of_nodes": 1,
        "project": "TG-MCB090174",
        "queue": "normal",
        "walltime": 59,
    }
    j = slurm_service.create_job(jd)
    j.run()
    print("Job State: " + j.get_state())
    j.cancel()
    print("Job State: " + j.get_state())
    
