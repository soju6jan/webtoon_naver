# -*- coding: utf-8 -*-
#########################################################
# python
import os
import sys
import traceback
import logging
import threading
import Queue
import json
# third-party

# sjva 공용
from framework import db, scheduler, path_data
from framework.job import Job
from framework.util import Util

# 패키지
import system
from .plugin import package_name, logger
from .model import ModelSetting, ModelItem
from .logic_normal import LogicNormal

#########################################################



class LogicQueue(object):
    download_queue = None
    download_thread = None
    entity_list = []

    @staticmethod
    def queue_start():
        try:
            if LogicQueue.download_queue is None:
                LogicQueue.download_queue = Queue.Queue()
            
            if LogicQueue.download_thread is None:
                LogicQueue.download_thread = threading.Thread(target=LogicQueue.download_thread_function, args=())
                LogicQueue.download_thread.daemon = True  
                LogicQueue.download_thread.start()
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def download_thread_function():
        while True:
            try:
                entity = LogicQueue.download_queue.get()
                logger.debug('Queue receive item:%s %s', entity['title_id'], entity['episode_id'])
                LogicNormal.download(entity)
                LogicQueue.download_queue.task_done()    
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())

    @staticmethod
    def add_queue(code, no):
        try:
            entity = ModelItem.init(code, no)
            if entity is not None:
                for idx, e in enumerate(LogicQueue.entity_list):
                    if e['id'] == entity['id']:
                        del LogicQueue.entity_list[idx]
                        #return
                if entity['status'] <= 10:
                    entity['str_status'] = u'대기'
                    LogicQueue.entity_list.append(entity)
                    LogicQueue.download_queue.put(entity)
                else:
                    LogicQueue.entity_list.append(entity)
            return entity
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    
    @staticmethod
    def completed_remove():
        try:
            new_list = []
            for e in LogicQueue.entity_list:
                if e['status'] <= 10:
                    new_list.append(e)
            LogicQueue.entity_list = new_list
            import plugin
            plugin.send_queue_list()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def reset_queue():
        try:
            with LogicQueue.download_queue.mutex:
                LogicQueue.download_queue.queue.clear()
            LogicQueue.entity_list = []
            import plugin
            plugin.send_queue_list()
            #LogicMD.stop()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

            
