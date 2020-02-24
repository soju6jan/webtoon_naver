# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback

# third-party
from flask import Blueprint, request, Response, send_file, render_template, redirect, jsonify, session, send_from_directory 
from flask_socketio import SocketIO, emit, send
from flask_login import login_user, logout_user, current_user, login_required

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler, path_data, socketio
from framework.util import Util
from system.logic import SystemLogic
from framework.common.torrent.process import TorrentProcess

# 패키지
# 로그
package_name = __name__.split('.')[0]
logger = get_logger(package_name)

from .model import ModelSetting, ModelItem
from .logic import Logic
from .logic_queue import LogicQueue
from .logic_normal import LogicNormal

#########################################################


#########################################################
# 플러그인 공용                                       
#########################################################
blueprint = Blueprint(package_name, package_name, url_prefix='/%s' %  package_name, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))

menu = {
    'main' : [package_name, '네이버 웹툰 다운로드'],
    'sub' : [
        ['setting', '설정'], ['request', '요청'], ['queue', '큐'], ['list', '목록'], ['log', '로그']
    ],
    'category' : 'service'
}

plugin_info = {
    'version' : '0.1.0.0',
    'name' : 'naver_webtoon',
    'category_name' : 'service',
    'developer' : 'soju6jan',
    'description' : '네이버 웹툰 다운로드',
    'home' : 'https://github.com/soju6jan/naver_webtoon',
    'more' : '',
}

def plugin_load():
    Logic.plugin_load()
    LogicQueue.queue_start()

def plugin_unload():
    Logic.plugin_unload()

def process_telegram_data(data):
    pass



#########################################################
# WEB Menu 
#########################################################
@blueprint.route('/')
def home():
    return redirect('/%s/request' % package_name)

@blueprint.route('/<sub>')
@login_required
def first_menu(sub): 
    arg = ModelSetting.to_dict()
    arg['package_name']  = package_name
    if sub == 'setting':
        arg['scheduler'] = str(scheduler.is_include(package_name))
        arg['is_running'] = str(scheduler.is_running(package_name))
        return render_template('%s_%s.html' % (package_name, sub), arg=arg)
    elif sub == 'request':
        if request.args.get('title_id') is not None:
            arg['recent_title_id'] = request.args.get('title_id')
        return render_template('%s_%s.html' % (package_name, sub), arg=arg)
    elif sub == 'queue':
        return render_template('%s_%s.html' % (package_name, sub), arg=arg)
    elif sub == 'list':
        return render_template('%s_%s.html' % (package_name, sub), arg=arg)
    elif sub == 'log':
        return render_template('log.html', package=package_name)
    return render_template('sample.html', title='%s - %s' % (package_name, sub))

#########################################################
# For UI 
#########################################################
@blueprint.route('/ajax/<sub>', methods=['GET', 'POST'])
@login_required
def ajax(sub):
    try:
        # 설정 저장
        if sub == 'setting_save':
            ret = ModelSetting.setting_save(request)
            return jsonify(ret)
        elif sub == 'scheduler':
            go = request.form['scheduler']
            logger.debug('scheduler :%s', go)
            if go == 'true':
                Logic.scheduler_start()
            else:
                Logic.scheduler_stop()
            return jsonify(go)
        elif sub == 'one_execute':
            ret = Logic.one_execute()
            return jsonify(ret)
        elif sub == 'reset_db':
            ret = Logic.reset_db()
            return jsonify(ret)  
        # 요청
        elif sub == 'analysis':
            code = request.form['code']
            page = request.form['page']
            ret = LogicNormal.analysis(code, page)
            if page == '1':
                ModelSetting.set('recent_title_id', code)
            return jsonify(ret)
        elif sub == 'add_queue':
            code = request.form['code']
            no = request.form['no']
            entity = LogicQueue.add_queue(code, no)
            if entity is not None:
                ret = 'success'
            else:
                ret = 'exist'
            return jsonify(ret)
        elif sub == 'add_queue_check':
            ret = {}
            code = request.form['code']
            data = request.form['no_list']

            logger.debug(data)
            no_list = data.split(',')
            count = 0
            for no in reversed(no_list):
                if no != '':
                    entity = LogicQueue.add_queue(code, no)
                    if entity is not None:
                        count += 1
            ret['ret'] = 'success'
            ret['log'] = count
            return jsonify(ret)
        # 큐
        elif sub == 'reset_queue':
            ret = LogicQueue.reset_queue()
            return jsonify(ret)
        elif sub == 'completed_remove':
            ret = LogicQueue.completed_remove()
            return jsonify(ret)
        # list
        elif sub == 'select':
            ret = ModelItem.select(request)
            return jsonify(ret)
        elif sub == 'list_remove':
            ret = ModelItem.delete(request)
            return jsonify(ret)
    except Exception as e: 
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())  
        return jsonify('fail')   




#########################################################
# socketio
#########################################################
sid_list = []
@socketio.on('connect', namespace='/%s' % package_name)
def connect():
    try:
        logger.debug('socket_connect')
        sid_list.append(request.sid)
        send_queue_list()
    except Exception as e: 
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())


@socketio.on('disconnect', namespace='/%s' % package_name)
def disconnect():
    try:
        sid_list.remove(request.sid)
        logger.debug('socket_disconnect')
    except Exception as e: 
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())

def socketio_callback(cmd, data, encoding=True):
    if sid_list:
        if encoding:
            data = json.dumps(data, cls=AlchemyEncoder)
            data = json.loads(data)
        socketio.emit(cmd, data, namespace='/%s' % package_name, broadcast=True)


def send_queue_list():
    logger.debug('send_queue_list')
    tmp = LogicQueue.entity_list
    #t = [x.as_dict() for x in tmp]
    #socketio_callback('queue_list', t, encoding=False)
    socketio_callback('queue_list', tmp, encoding=False)
