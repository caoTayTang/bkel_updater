from dotenv import load_dotenv
import os

import requests
from requests.structures import CaseInsensitiveDict
from bs4 import BeautifulSoup, Tag
import time

load_dotenv()

USER_NAME = os.getenv('USER_NAME')
PASSWORD = os.getenv('PASSWORD')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# use to grab grades view
LMS_USER_ID = os.getenv('LMS_USER_ID')

DEBUG = False
LMS_URL = 'https://lms.hcmut.edu.vn/'

course_link = []
course_data= []
course_grades = []

s = requests.session()


def login_sso():
    SSO_URL = 'https://sso.hcmut.edu.vn/cas/login?service=https://mybk.hcmut.edu.vn/my/homeSSO.action'
    headers = CaseInsensitiveDict()
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    response = s.get(SSO_URL, headers=headers).text

    lt = response.split('<input type="hidden" name="lt" value="')[1].split('" />')[0]
    execution = response.split('<input type="hidden" name="execution" value="')[1].split('" />')[0]
    data = f'username={USER_NAME}&password={PASSWORD}&execution={execution}&_eventId=submit&submit=Login&lt={lt}'
    s.post(SSO_URL, headers=headers, data=data)

def crawl_courses_link():
    global course_link
    login = s.get('https://lms.hcmut.edu.vn/login/index.php?authCAS=CAS')

    if 'Error: Database connection failed' not in login.text:
        sess_key = login.text.split('sesskey=')[1].split('"')[0]

        get_course = s.post(
                f'https://lms.hcmut.edu.vn/lib/ajax/service.php?sesskey={sess_key}&info=core_course_get_enrolled_courses_by_timeline_classification',
                json=[{
                        "index": 0,
                        "methodname":
                        "core_course_get_enrolled_courses_by_timeline_classification",
                        "args": {
                                "offset": 0,
                                "limit": 0,
                                "classification": "all",
                                "sort": "fullname",
                                "customfieldname": "",
                                "customfieldvalue": ""
                        }
                }])

        if get_course.json()[0]['error'] == False:
            for course in get_course.json()[0]['data']['courses']:
                if str(course['id']) not in course_link:
                    course_link.append({'viewurl': course['viewurl'],
                        'id': course['id'],
                        'fullname': course['fullname']
                    })
        return sess_key




# If the ret is empty then cannot .get_text so make a default to be ''
def helper_get_grade(row, _class): 
    ret = row.select_one(f'.{_class}') 
    ret = ret.get_text(strip=True) if ret else ''
    return ret

def crawl_grades_view(course_grades):
    for course in course_link:
        url = f'https://lms.hcmut.edu.vn/course/user.php?mode=grade&id={course['id']}&user={LMS_USER_ID}'
        body = BeautifulSoup(s.get(url).text, 'html.parser').find('tbody')
        if isinstance(body, Tag):
            rows = body.find_all('tr')
            grade_course_list = []
            for row in rows:
                grade_item = row.select_one('.gradeitemheader')
                if grade_item:
                    grade_item = grade_item.get_text(strip=True)
                    calculated_weight = helper_get_grade(row, 'column-weight')
                    grade = helper_get_grade(row, 'column-grade')
                    range_grade = helper_get_grade(row, 'column-range')
                    percentage = helper_get_grade(row, 'column-percentage')
                    feedback = helper_get_grade(row, 'column-feedback')
                    contribute_to_course_totol = helper_get_grade(row, 'column-contributiontocoursetotal')

                    grade_course_list.append({
                        'grade_item': f'{grade_item}',
                        'calulated_weight': calculated_weight,
                        'grade': grade,
                        'range': range_grade,
                        'percentage': percentage,
                        'feedback': feedback,
                        'contribute_to_course_total': contribute_to_course_totol
                    })

            course_grades.append({
                'id': f'{course['id']}',
                'course_name': f'{course['fullname']}',
                'total_grade': grade_course_list
            })


def crawl_data_course(): 
    global course_data
    for link in course_link:
        data = BeautifulSoup(s.get(link['viewurl']).text, 'html.parser').select_one('ul.topics[data-for="course_sectionlist"]')

        json = {
            'id': link['viewurl'].split('id=')[1],
            'data': data
        }

        course_data.append(json)

def convert_to_json(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')

    uls = soup.find_all('ul', class_ = 'topics')

    parsed_data = []

    for ul in uls:
        lis = ul.find_all('li', class_ = 'section', recursive = False)
        for li in lis:
            # extract the section number from the data-sectionid attribute
            section_number = li.get('data-sectionid', 0)

            # find all the cmitem elements within the section
            cm_items = li.find_all('li', attrs={
                'data-for': 'cmitem'
            })

            for cm_item in cm_items:
                item_id = cm_item.get('data-id')
                a_tag = cm_item.find('a', href = True)

                if a_tag and 'href' in a_tag.attrs:
                    url = a_tag['href']
                else:
                    url = ''

                title = None
                title_area = cm_item.find('div', class_="activity-name-area")
                if title_area:
                    title = title_area.get_text(strip=False)
                if not title:
                    title = cm_item.get_text(strip=True)

                # Append the parsed data to the list
                parsed_data.append({
                    "section": int(section_number),
                    "data": {
                        "item": int(item_id),
                        "title": title.strip(),
                        "url": url
                    }
                })
    return parsed_data

def compare_json(old, new):
    # Convert the old data into a set of item IDs for faster lookup
    old_item_ids = set(item['data']['item'] for item in old)
    new_items = []
    for item in new:
        # Check if the item ID is not in the set of old item IDs
        if item['data']['item'] not in old_item_ids:
            new_items.append(item)
    return new_items


def notify_grade(url, title, embed_content, color=16718362, tag = True):
    USER_ID = '565749600787365918'
    content = f"<@!{USER_ID}> Check this out!!!" if tag else ""
    payload = {
            "content": content,
            "embeds": [{
                    "title": f'{title}',
                    "description": embed_content,
                    "color": f'{color}' ,
                    "url": url
            }],
            "components": [],
            "actions": {},
            "username": "LMS Update",
            "avatar_url": 'https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png '
    }

    response = requests.post(str(WEBHOOK_URL), json=payload)

    if response.status_code == 204:
        print(f"Message sent for {title}")
    else:
        print(f"Failed to send message for {title}")

def notify(item):
    title = item['data']['title']
    url = item['data']['url']
    USER_ID = '565749600787365918'

    payload = {
            "content": f"<@!{USER_ID}> Check this out!!!",
            "embeds": [{
                    "title": f"{title}",
                    "description": "Mới up gì kìa :new:",
                    "color": 3308528,
                    "url": url
            }],
            "components": [],
            "actions": {},
            "username": "LMS Update",
            "avatar_url": 'https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png '
    }

    response = requests.post(str(WEBHOOK_URL), json=payload)

    if response.status_code == 204:
        print(f"Message sent for {title}")
    else:
        print(f"Failed to send message for {title}")


def recheck_grade():
    global course_grades
    nothingChange = True

    new_grades = []
    crawl_grades_view(new_grades)

    diff_results = []
    for i in range(len(new_grades)): # each course
        old_set = set(course_grades[i]['total_grade'][each]['grade_item'] for each in range(len(course_grades[i]['total_grade'])))
        new_set = set(new_grades[i]['total_grade'][each]['grade_item'] for each in range(len(new_grades[i]['total_grade'])))
        diff_set = new_set.difference(old_set)

        # In case of newly added item or change in grade_item
        for value in diff_set: 
            nothingChange = False
            print("New item added")
            diff_results.append({
                'url': f'https://lms.hcmut.edu.vn/course/user.php?mode=grade&id={course_grades[i]['id']}&user={LMS_USER_ID}',
                'title': f'{course_grades[i]['course_name']}', 
                'content': 
                f"""
                                **Điểm số có thay đổi kìa :scream_cat:**

                                *Nội dung thay đổi*: {value}
                            """
            })
        if len(diff_set): continue

        for each in range(len(new_grades[i]['total_grade'])): # each module in a course
            for key in new_grades[i]['total_grade'][each].keys():
                old_value = course_grades[i]['total_grade'][each].get(key)
                new_value = new_grades[i]['total_grade'][each].get(key)

                if new_value != old_value:
                    nothingChange = False

                    print("New item added")
                    diff_results.append({
                        'url': f'https://lms.hcmut.edu.vn/course/user.php?mode=grade&id={course_grades[i]['id']}&user={LMS_USER_ID}',
                        'title': f'{course_grades[i]['course_name']}', 
                        'content': 
                            f"""
                                **Điểm số có thay đổi kìa :scream_cat:**

                                *Nội dung thay đổi*: {new_grades[i]['total_grade'][each]['grade_item']}
                                *Điểm cũ*: ~~{old_value}~~
                                *Điểm mới*: {new_value}
                            """
                    })

    for result in diff_results:
        notify_grade(result['url'], result['title'], result['content'])
        time.sleep(1)

    course_grades = new_grades
    return nothingChange

def recheck_data():
    global course_data
    nothingChange = True

    for i in range(len(course_data)):
        view_url = 'https://lms.hcmut.edu.vn/course/view.php?id=' + course_data[i]['id']
        data = BeautifulSoup(s.get(view_url).text, 'html.parser').select_one('ul.topics[data-for="course_sectionlist"]')

        json = {
            'id': str(course_data[i]['id']),
            'data': data
        }

        if str(data) not in str(course_data[i]['data']):
            json_old = convert_to_json(str(course_data[i]['data']))
            json_new = convert_to_json(str(data))
            diff_result = compare_json(json_old, json_new)

            if len(diff_result):
                nothingChange = False
                print("New item added")

            for result in diff_result:
                notify(result)
                time.sleep(1)

            course_data[i] = json
        elif DEBUG:
            json_old = convert_to_json(str(course_data[i]['data']))
            for result in json_old:
                notify(result)
                time.sleep(2)

    if recheck_grade() and nothingChange: 
        notify_grade(url='', title='Nothing changes', embed_content='Chill đi bạn ưi :face_exhaling:', color = 3308528, tag = False)

login_sso() 
sess_key = crawl_courses_link()

crawl_data_course()
crawl_grades_view(course_grades)


#import json
# with open('foo/grades.json', '+w', encoding = 'utf8') as file:
#     js_string = json.dumps(course_grades, indent=4, ensure_ascii=False)
#     file.write(js_string)

#TODO: Check DMs
hour = 3
while True:
    recheck_data()
    time.sleep(hour*60*60) # 3 hour
