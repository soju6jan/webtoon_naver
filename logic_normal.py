# -*- coding: utf-8 -*-
#########################################################
# python
import os
import datetime
import traceback
import urllib
from datetime import datetime


# third-party
from sqlalchemy import desc
from sqlalchemy import or_, and_, func, not_
import requests
from lxml import html
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

# sjva 공용
from framework import app, db, scheduler, path_app_root, celery
from framework.job import Job
from framework.util import Util


# 패키지
from .plugin import logger, package_name
from .model import ModelSetting, ModelItem

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3578.98 Safari/537.36',
    'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language' : 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer' : ''
} 



#########################################################
class LogicNormal(object):
    session = requests.Session()
    driver = None

    @staticmethod
    def scheduler_function():
        # 자동 추가 목록에 따라 큐에 집어넣음.
        try:
            whitelists = [x.strip().replace(' ', '') for x in ModelSetting.get('whitelist').replace('\n', '|').split('|')]
            whitelists = Util.get_list_except_empty(whitelists)

            blacklists = [x.strip().replace(' ', '') for x in ModelSetting.get('blacklist').replace('\n', '|').split('|')]
            blacklists = Util.get_list_except_empty(blacklists)

            url = 'https://comic.naver.com/webtoon/weekday.nhn'
            data = LogicNormal.get_html(url)
            tree = html.fromstring(data)
            tags = tree.xpath('//div[@class="thumb"]')
            logger.debug(whitelists)
            for tag in tags:
                href = tag.xpath('a')[0].attrib['href']
                em = tag.xpath('a/em')
                if em:
                    if em[0].attrib['class'] == 'ico_updt':
                        title = tag.xpath('following-sibling::a')[0].attrib['title'].strip()
                        title_id = href.split('titleId=')[1].split('&')[0].strip()
                        flag = False
                        if len(whitelists) == 0 or title.replace(' ', '') in whitelists:
                            flag = True
                        if flag and len(blacklists) > 0 and title.replace(' ', '') in blacklists:
                            flag = False
                        #logger.debug(title)
                        #logger.debug(flag)
                        if flag:
                            data = LogicNormal.analysis(title_id, '1')
                            if data['ret'] == 'success':
                                last_entity = ModelItem.get(title_id, data['episodes'][0]['no'])
                                if last_entity is None:
                                    from .logic_queue import LogicQueue
                                    LogicQueue.add_queue(title_id, data['episodes'][0]['no'])
                                    
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def scheduler_function_db():
        #return
        # 실패, 대기 목록을 큐에 집어넣음
        entities = db.session.query(ModelItem).filter(ModelItem.status<10).all()
        from .logic_queue import LogicQueue
        for e in entities:
            e.status_kor = u'대기'
            #e.status_kor = u'대기'
            entity = LogicQueue.add_queue(e.title_id, e.episode_id)


    @staticmethod
    def analysis(code, page):
        ret = {}
        try:
            url = 'https://comic.naver.com/webtoon/list.nhn?titleId=%s&page=%s' % (code, page)
            data = LogicNormal.get_html(url)
            tree = html.fromstring(data)
            base_div = '//*[@id="content"]/div[1]'
            if not tree.xpath('%s/div[1]/a/img' % base_div):
                base_div = '//*[@id="content"]/div[2]'

            ret['image'] = tree.xpath('%s/div[1]/a/img' % base_div)[0].attrib['src']
            ret['title'] = tree.xpath('%s/div[2]/h2/text()' % base_div)[0].strip()
            ret['author'] = tree.xpath('%s/div[2]/h2/span' % base_div)[0].text_content().strip()
            ret['desc'] = tree.xpath('%s/div[2]/p' % base_div)[0].text_content().strip()

            tr = tree.xpath('//*[@id="content"]/table/tr')
            #logger.debug(len(tr))
            ret['episodes'] = []
            for i in range(1, len(tr)):
                try:
                    #logger.debug(i)
                    entity = {}
                    td = tr[i].xpath('td[1]/a')[0]
                    entity['href'] = td.attrib['href']

                    td = tr[i].xpath('td[1]/a/img')[0]
                    entity['image'] = td.attrib['src']

                    entity['episode_title'] = tr[i].xpath('td[2]')[0].text_content().strip()
                    entity['rating'] = tr[i].xpath('td[3]')[0].text_content().strip()
                    entity['date'] = tr[i].xpath('td[4]')[0].text_content().strip()
                    entity['no'] = entity['href'].split('no=')[1].split('&')[0]
                    ret['episodes'].append(entity)
                except:
                    pass

            ret['is_next'] = (data.find('<span class="cnt_page">다음</span>') != -1)
            ret['page'] = page
            ret['code'] = code
            ret['ret'] = 'success'
            #logger.debug(ret)
            
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret['ret'] = 'exception'
            ret['log'] = str(e)
        return ret


    @staticmethod
    def get_html(url, referer=None, stream=False):
        try:
            if LogicNormal.session is None:
                LogicNormal.session = requests.session()
            #logger.debug('get_html :%s', url)
            headers['Referer'] = '' if referer is None else referer
            page_content = LogicNormal.session.get(url, headers=headers)
            data = page_content.content
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        return data

    @staticmethod
    def download(entity):
        try:
            if app.config['config']['use_celery']:
                result = LogicNormal.download2.apply_async((entity,))
                #result.get()
                try:
                    result.get(on_message=LogicNormal.update, propagate=True)
                except:
                    logger.debug('CELERY on_message not process.. only get() start')
                    try:
                        result.get()
                    except:
                        pass
            else:
                LogicNormal.download2(entity)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def update(arg):
        logger.debug('FOR update : %s' % arg)
        if arg['status'] == 'PROGRESS':
            result = arg['result']
            LogicNormal.entity_update(result['data']) 
            from .logic_queue import LogicQueue
            for idx, e in enumerate(LogicQueue.entity_list):
                if e['id'] == result['data']['id']:
                    LogicQueue.entity_list[idx] = result['data']
                    break

    @staticmethod
    def entity_update(entity):
        import plugin
        plugin.socketio_callback('queue_one', entity, encoding=False)
    
    @staticmethod
    def update_ui(celery_is, entity):
        if app.config['config']['use_celery']:
            
            celery_is.update_state(state='PROGRESS', meta={'data':entity})
            
        else:
            LogicNormal.entity_update(entity)

    @staticmethod
    @celery.task(bind=True)
    def download2(self, entity):
        try:
            from system import LogicSelenium
            import plugin
            if LogicNormal.driver is None:
                LogicNormal.driver = LogicSelenium.create_driver()

            driver = LogicNormal.driver
            url = 'https://comic.naver.com/webtoon/detail.nhn?titleId=%s&no=%s' % (entity['title_id'], entity['episode_id'])
            ret = False

            driver.get(url)
            entity['download_count'] += 1
            entity['status'] = 1
            entity['str_status'] = '대기'
            LogicNormal.update_ui(self, entity)

            tag = WebDriverWait(driver, 30).until(lambda driver: driver.find_element_by_xpath('//*[@id="content"]/div[1]/div[1]/div[2]/h2'))
            entity['title'] = LogicSelenium.get_text_excluding_children(driver, tag).strip()

            tag = WebDriverWait(driver, 30).until(lambda driver: driver.find_element_by_xpath('//*[@id="content"]/div[1]/div[2]/div[1]/h3'))
            entity['episode_title'] = tag.text
            entity['str_status'] = '분석'
            LogicNormal.update_ui(self, entity)

            tag = WebDriverWait(driver, 30).until(lambda driver: driver.find_element_by_xpath('//*[@id="btnRemoteConOnOff"]'))
            if tag.find_element_by_xpath('em').text == 'ON':
                #logger.debug('ON to OFF')
                tag.click()
            #S = lambda X: driver.execute_script('return document.body.parentNode.scroll'+X)
            #driver.set_window_size(S('Width'),S('Height')) # May need manual adjustment  
            #logger.debug(S('Width'))        
            #logger.debug(S('Height'))        


            tag = WebDriverWait(driver, 30).until(lambda driver: driver.find_element_by_xpath('//*[@id="comic_view_area"]/div[1]'))

            dirname = ModelSetting.get('download_path')
            if ModelSetting.get_bool('use_title_folder'):
                dirname = os.path.join(dirname, Util.change_text_for_use_filename(entity['title']))
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            tmp = u'%s %s.png' % (entity['title'], entity['episode_title'])
            entity['filename'] = os.path.join(dirname, Util.change_text_for_use_filename(tmp))
            if os.path.exists(entity['filename']):
                entity['status'] = 12
                entity['str_status'] = '파일 있음'
                LogicNormal.update_ui(self, entity)
            else:
                entity['str_status'] = '다운로드중'
                LogicNormal.update_ui(self, entity)
                full = LogicSelenium.full_screenshot(driver)
                img_tag = tag.find_elements_by_xpath('img')
                if len(img_tag) > 1:
                    img_tag = img_tag[1]
                elif len(img_tag) == 1:
                    img_tag = img_tag[0]
                else:
                    pass
                left = img_tag.location['x']
                top = tag.location['y']
                right = img_tag.location['x'] + img_tag.size['width']
                bottom = tag.location['y'] + tag.size['height']

                
                im = full.crop((left, top, right, bottom)) # defines crop points
                im.save(entity['filename'])
                entity['status'] = 11
                entity['str_status'] = '완료'
                LogicNormal.update_ui(self, entity)
            
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            entity['status'] = 2
            entity['str_status'] = '실패'
            if entity['download_count'] >= 20:
                entity['status'] = 13
                entity['str_status'] = '재시도초과'
            LogicNormal.update_ui(self, entity)
        
        ModelItem.save_as_dict(entity)
        
            


    