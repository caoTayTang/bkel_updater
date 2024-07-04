from dotenv import load_dotenv
import os

import requests
from requests.structures import CaseInsensitiveDict
from bs4 import BeautifulSoup, Tag
import time
import json

load_dotenv()

USER_NAME = os.getenv('USER_NAME')
PASSWORD = os.getenv('PASSWORD')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# use to grab grades view
USER_ID = 11915

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
    login_response = s.post(SSO_URL, headers=headers, data=data)

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
        url = f'https://lms.hcmut.edu.vn/course/user.php?mode=grade&id={course['id']}&user={USER_ID}'
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


def crawl_data_course(sess_key): 
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
    #crawl_grades_view(new_grades)
    new_grades = [
    {
        "id": "29619",
        "course_name": "Cấu trúc Rời rạc cho Khoa học Máy tính (CO1007)_Trần Hồng Tài (CQ_HK232) [L04]",
        "total_grade": [
            {
                "grade_item": "Quiz 1",
                "calulated_weight": "-",
                "grade": "8,67",
                "range": "0–10",
                "percentage": "86,67 %",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "Quiz 2",
                "calulated_weight": "-",
                "grade": "10",
                "range": "0–10",
                "percentage": "86,67 %",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–20",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "5167",
        "course_name": "Cấu trúc Rời rạc cho Khoa học Máy tính (CO1007)_Video",
        "total_grade": [
            {
                "grade_item": "BF, BF_PATH (Input mẫu - không tính điểm)",
                "calulated_weight": "11,11 %",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "11,11 %"
            },
            {
                "grade_item": "BF",
                "calulated_weight": "11,11 %",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "11,11 %"
            },
            {
                "grade_item": "BF_PATH",
                "calulated_weight": "11,11 %",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "11,11 %"
            },
            {
                "grade_item": "Traveling_size8",
                "calulated_weight": "11,11 %",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "11,11 %"
            },
            {
                "grade_item": "Traveling_size10",
                "calulated_weight": "11,11 %",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "11,11 %"
            },
            {
                "grade_item": "Traveling_size12",
                "calulated_weight": "11,11 %",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "11,11 %"
            },
            {
                "grade_item": "Traveling_size14",
                "calulated_weight": "11,11 %",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "11,11 %"
            },
            {
                "grade_item": "Traveling_size16",
                "calulated_weight": "11,11 %",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "11,11 %"
            },
            {
                "grade_item": "Traveling (Input mẫu - không tính điểm)",
                "calulated_weight": "11,11 %",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "11,11 %"
            },
            {
                "grade_item": "Nộp các file code và báo cáo",
                "calulated_weight": "0,00 %( Empty )",
                "grade": "-",
                "range": "0–100",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "0,00 %"
            },
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "90,00",
                "range": "0–90",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "30899",
        "course_name": "Đại số Tuyến tính (MT1007)_NGUYỄN HỮU HIỆP (CQ_HK232) [L10,L14,L15]",
        "total_grade": [
            {
                "grade_item": "Điểm Bài tập",
                "calulated_weight": "0,00 %( Empty )",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "0,00 %"
            },
            {
                "grade_item": "Điểm giữa kỳ",
                "calulated_weight": "100,00 %",
                "grade": "8,50",
                "range": "0–10",
                "percentage": "85,00 %",
                "feedback": "",
                "contribute_to_course_total": "85,00 %"
            },
            {
                "grade_item": "Điểm BTL",
                "calulated_weight": "0,00 %( Empty )",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "0,00 %"
            },
            {
                "grade_item": "Điểm thi",
                "calulated_weight": "0,00 %( Empty )",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "0,00 %"
            },
            {
                "grade_item": "Link nộp bài tập lớn",
                "calulated_weight": "0,00 %( Empty )",
                "grade": "-",
                "range": "0–100",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "0,00 %"
            },
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "8,50",
                "range": "0–10",
                "percentage": "85,00 %",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "7931",
        "course_name": "Đại số Tuyến tính (MT1007)_Video",
        "total_grade": [
            {
                "grade_item": "Điểm Giữa kỳ",
                "calulated_weight": "-",
                "grade": "8,50",
                "range": "0–10",
                "percentage": "85,00 %",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–80",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "15179",
        "course_name": "Giải tích 2 (Bài tập) (MT1006)_Đoàn Thị Thanh Xuân (CQ_HK232) [L22,L32,L38,L42]",
        "total_grade": [
            {
                "grade_item": "Nộp BTL L38",
                "calulated_weight": "0,00 %( Empty )",
                "grade": "-",
                "range": "0–100",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "0,00 %"
            },
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–100",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "9811",
        "course_name": "Giải tích 2 (Bài tập) (MT1006)_Video",
        "total_grade": [
            {
                "grade_item": "Bài tập rèn luyện",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–17",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–17",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "16527",
        "course_name": "Giải tích 2 (MT1005)_TRẦN NGỌC DIỄM (CQ_HK232) [L03,L07,L15,L19,L23]",
        "total_grade": [
            {
                "grade_item": "QUIZ 1",
                "calulated_weight": "",
                "grade": "9,90",
                "range": "0,00–10,00",
                "percentage": "99,00 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 1",
                "calulated_weight": "",
                "grade": "9,90",
                "range": "0,00–10,00",
                "percentage": "99,00 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 2",
                "calulated_weight": "",
                "grade": "4,50",
                "range": "0,00–6,00",
                "percentage": "75,00 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 3",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–6,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 1 (a)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 2 (a)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–5,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 3 (a)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 4(a)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 5(a)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 1 (a)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 2 (a)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–5,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 3 (a)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 4(a)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 5(a)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 4(L07)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 5(L07)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 1 (L07)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 2 (L07)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 2",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–6,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST1",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST2",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST2",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST3",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST4",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST1",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST1",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST1",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST2",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST1",
                "calulated_weight": "",
                "grade": "10,00",
                "range": "0,00–10,00",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST2",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST2",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 2 (thang 10)",
                "calulated_weight": "",
                "grade": "7,50",
                "range": "0,00–100,00",
                "percentage": "7,50 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 3 (Copy)",
                "calulated_weight": "",
                "grade": "8,30",
                "range": "0,00–10,00",
                "percentage": "83,00 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 3 (L07)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–9,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ - REVIEW 1",
                "calulated_weight": "",
                "grade": "5,00",
                "range": "0,00–5,00",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ - REVIEW 2 (Chuỗi)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–12,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 4 (Copy)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 5",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 4 (Copy)",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 5",
                "calulated_weight": "",
                "grade": "9,30",
                "range": "0,00–10,00",
                "percentage": "93,00 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST3",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST3",
                "calulated_weight": "",
                "grade": "9,00",
                "range": "0,00–10,00",
                "percentage": "90,00 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST4",
                "calulated_weight": "",
                "grade": "9,00",
                "range": "0,00–9,00",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST4",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–9,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "NỘP BÀI TẬP LỚN",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–100,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST3",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST4",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–10,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST4",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–9,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST4",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–9,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "PRETEST4",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–9,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ6",
                "calulated_weight": "",
                "grade": "7,70",
                "range": "0,00–9,00",
                "percentage": "85,56 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "QUIZ 7",
                "calulated_weight": "",
                "grade": "12,00",
                "range": "0,00–10,00",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "Điểm 5%",
                "calulated_weight": "",
                "grade": "10,0",
                "range": "0,00–10,00",
                "percentage": "95,00 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "Điểm 20%",
                "calulated_weight": "",
                "grade": "10,00",
                "range": "0,00–10,00",
                "percentage": "100,00 %",
                "feedback": "10",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "Điểm 25%",
                "calulated_weight": "",
                "grade": "8,50",
                "range": "0,00–13,00",
                "percentage": "65,38 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "Điểm 50%",
                "calulated_weight": "",
                "grade": "10,00",
                "range": "0,00–13,00",
                "percentage": "76,92 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "Điểm tổng kết",
                "calulated_weight": "",
                "grade": "9,60",
                "range": "0,00–10,00",
                "percentage": "96,00 %",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "",
                "grade": "-",
                "range": "0,00–355,00",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": ""
            }
        ]
    },
    {
        "id": "5147",
        "course_name": "Giải tích 2 (MT1005)_Video",
        "total_grade": [
            {
                "grade_item": "Bài tập rèn luyện số 1",
                "calulated_weight": "",
                "grade": "20,00",
                "range": "",
                "percentage": "",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "Điễm GHK232",
                "calulated_weight": "",
                "grade": "8,58",
                "range": "",
                "percentage": "",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "Điểm CHK232",
                "calulated_weight": "",
                "grade": "10,00",
                "range": "",
                "percentage": "",
                "feedback": "",
                "contribute_to_course_total": ""
            },
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "",
                "grade": "38,58",
                "range": "",
                "percentage": "",
                "feedback": "",
                "contribute_to_course_total": ""
            }
        ]
    },
    {
        "id": "31071",
        "course_name": "KỸ THUẬT LẬP TRÌNH (CO1027)_HK232_ALL",
        "total_grade": [
            {
                "grade_item": "Assignment 1 - Submission",
                "calulated_weight": "-",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "Breakdown:+Task 'firstMeet': 1.50+Task 'traceLuggae': 2.50+Task 'chaseTaxi': 3.00+Task 'checkPassword': 1.50+Task 'findCorrectPassword': 1.50",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "Assignment 1 - Nộp lại",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "Assignment 2 - Submission",
                "calulated_weight": "-",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "Assignment 2 - Final score",
                "calulated_weight": "-",
                "grade": "6,82",
                "range": "0–10",
                "percentage": "68,20 %",
                "feedback": "Breakdown:+ Task 'Path, Wall, FakeWall, Position': 1.48+ Task 'Characture': 0.80+ Task 'ArrayMovingObject': 0.50+ Task 'Configuration': 0.39+ Task 'Rboot': 0.67+ Task 'Item': 1.33+ Task 'Bag': 0.23+ Task 'StudyPinkProgram': 1.08Raw score: 6.48",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–40",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "13551",
        "course_name": "Kỹ thuật Lập trình (CO1027)_TRẦN GIANG SƠN (CQ_HK232) [L01]",
        "total_grade": [
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–0",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "8139",
        "course_name": "Kỹ thuật Lập trình (CO1027)_Video",
        "total_grade": [
            {
                "grade_item": "Bài giảng",
                "calulated_weight": "-",
                "grade": "14,00",
                "range": "0–100",
                "percentage": "14,00 %",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "Struct (User-defined data types)",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–100",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "Array",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–100",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "SCORM: String",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–100",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "SCORM: Function (P.1)",
                "calulated_weight": "-",
                "grade": "0,00",
                "range": "0–100",
                "percentage": "0,00 %",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–200",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "31275",
        "course_name": "KỸ THUẬT LẬP TRÌNH (CO1028)_HK232_ALL",
        "total_grade": [
            {
                "grade_item": "SEB - Sample Test",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "L20",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "Điểm danh",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "DT01",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "L03",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "CC13",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "CC10",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "CC01",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "CC05",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "CC14",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "CC04",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "CC09",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "CC12",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "CC04 (NO SEB)",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "CC12 (NO SEB)",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "Assignment 1",
                "calulated_weight": "-",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "Breakdown:+Task 'firstMeet': 1.50+Task 'traceLuggae': 2.50+Task 'chaseTaxi': 3.00+Task 'checkPassword': 1.50+Task 'findCorrectPassword': 1.50",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "Assignment tổng cộng",
                "calulated_weight": "3,33 %",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "L06",
                "calulated_weight": "-",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "L13",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "L12",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            },
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–300",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "48483",
        "course_name": "Kỹ thuật Lập trình (TN) (CO1028)_LÊ BÌNH ĐẲNG (CQ_HK232) [L06,L13]",
        "total_grade": [
            {
                "grade_item": "Điểm danh",
                "calulated_weight": "71,43 %",
                "grade": "90,00",
                "range": "0–100",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "71,43 %"
            },
            {
                "grade_item": "Test SEB",
                "calulated_weight": "7,14 %",
                "grade": "20,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "7,14 %"
            },
            {
                "grade_item": "[L13] Lab Test 06/6/2024",
                "calulated_weight": "0,00 %( Empty )",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "0,00 %"
            },
            {
                "grade_item": "[L13] Lab Test 06/6/2024 - No SEB",
                "calulated_weight": "0,00 %( Empty )",
                "grade": "-",
                "range": "0–10",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "0,00 %"
            },
            {
                "grade_item": "Lab Week",
                "calulated_weight": "7,14 %",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "7,14 %"
            },
            {
                "grade_item": "Lab Test",
                "calulated_weight": "7,14 %",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "7,14 %"
            },
            {
                "grade_item": "Lab Overall",
                "calulated_weight": "7,14 %",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "7,14 %"
            },
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "140,00",
                "range": "0–140",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "6271",
        "course_name": "Kỹ thuật Lập trình (TN) (CO1028)_Video",
        "total_grade": [
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–0",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "41847",
        "course_name": "Lớp Chủ nhiệm (LCN)_NGUYỄN QUANG ĐỨC (CQ_HK232)",
        "total_grade": [
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–0",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "44767",
        "course_name": "Sinh hoạt Sinh viên (SA0001)_NGUYỄN QUANG ĐỨC (CQ_HK232) [L27]",
        "total_grade": [
            {
                "grade_item": "Attendance",
                "calulated_weight": "100,00 %",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "100,00 %"
            },
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "10,00",
                "range": "0–10",
                "percentage": "100,00 %",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "43999",
        "course_name": "Sinh hoạt Sinh viên (SA0001)_Video",
        "total_grade": [
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–0",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "12543",
        "course_name": "Thí nghiệm Vật lý (PH1007)_NGUYỄN  ĐÌNH QUANG (CQ_HK232) [L02,L05,L06,L07,L08,L09,L10,L16,L17,L21,L27,L33]",
        "total_grade": [
            {
                "grade_item": "Tổng khóa học",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–0",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    },
    {
        "id": "6091",
        "course_name": "Thí nghiệm Vật lý (PH1007)_Video",
        "total_grade": [
            {
                "grade_item": "Thay doi mot ti ne",
                "calulated_weight": "-",
                "grade": "-",
                "range": "0–0",
                "percentage": "-",
                "feedback": "",
                "contribute_to_course_total": "-"
            }
        ]
    }
]


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
                'url': f'https://lms.hcmut.edu.vn/course/user.php?mode=grade&id={course_grades[i]['id']}&user={USER_ID}',
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
                        'url': f'https://lms.hcmut.edu.vn/course/user.php?mode=grade&id={course_grades[i]['id']}&user={USER_ID}',
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

crawl_data_course(sess_key)
crawl_grades_view(course_grades)


# with open('foo/grades.json', '+w', encoding = 'utf8') as file:
#     js_string = json.dumps(course_grades, indent=4, ensure_ascii=False)
#     file.write(js_string)

hour = 3
while True:
    recheck_data()
    time.sleep(hour*60*60) # 3 hour
