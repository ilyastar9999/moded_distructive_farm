import re
import time
from datetime import datetime

from flask import jsonify, render_template, request, redirect

from __init__ import app
import auth
import database
import reloader
from models import FlagStatus


@app.template_filter('timestamp_to_datetime')
def timestamp_to_datetime(s):
    return datetime.fromtimestamp(s)

@app.route('/', methods=['GET', 'POST'])
def index_redirect():
    if request.method == 'POST':
        response = redirect('/')
        response.set_cookie('password', request.form['password'])
        return response
    config = reloader.get_config()
    if request.cookies.get('password') == config['SERVER_PASSWORD']:
        return redirect('/farm')
    return render_template('hello.html')

@app.route('/farm')
@auth.auth_required
def index():
    distinct_values = {}
    for column in ['sploit', 'status', 'team']:
        rows = database.query('SELECT DISTINCT {} FROM flags ORDER BY {}'.format(column, column))
        distinct_values[column] = [item[column] for item in rows]  # Access by key, not index

    config = reloader.get_config()

    server_tz_name = time.strftime('%Z')
    if server_tz_name.startswith('+'):
        server_tz_name = 'UTC' + server_tz_name

    return render_template('index.html',
                           flag_format=config['FLAG_FORMAT'],
                           distinct_values=distinct_values,
                           server_tz_name=server_tz_name)


FORM_DATETIME_FORMAT = '%Y-%m-%d %H:%M'
FLAGS_PER_PAGE = 30

@app.route('/ui/show_flags', methods=['POST'])
@auth.auth_required
def show_flags():
    conditions = []
    for column in ['sploit', 'status', 'team']:
        value = request.form[column]
        if value:
            conditions.append(('{} = %s'.format(column), value))
    for column in ['flag', 'checksystem_response']:
        value = request.form[column]
        if value:
            conditions.append(('LOWER({}) LIKE %s'.format(column), '%' + value.lower() + '%'))  # Changed INSTR to LIKE
    for param in ['time-since', 'time-until']:
        value = request.form[param].strip()
        if value:
            timestamp = round(datetime.strptime(value, FORM_DATETIME_FORMAT).timestamp())
            sign = '>=' if param == 'time-since' else '<='
            conditions.append(('time {} %s'.format(sign), timestamp))
    page_number = int(request.form['page-number'])
    if page_number < 1:
        raise ValueError('Invalid page-number')

    if conditions:
        chunks, values = list(zip(*conditions))
        conditions_sql = 'WHERE ' + ' AND '.join(chunks)
        conditions_args = list(values)
    else:
        conditions_sql = ''
        conditions_args = []

    sql = 'SELECT * FROM flags ' + conditions_sql + ' ORDER BY time DESC LIMIT %s OFFSET %s'
    args = conditions_args + [FLAGS_PER_PAGE, FLAGS_PER_PAGE * (page_number - 1)]
    flags = database.query(sql, args)

    sql = 'SELECT COUNT(*) as count FROM flags ' + conditions_sql  # Added alias
    args = conditions_args
    total_count_result = database.query(sql, args)
    total_count = total_count_result[0]['count'] if total_count_result else 0  # Access by key

    return jsonify({
        'rows': [dict(item) for item in flags],
        'rows_per_page': FLAGS_PER_PAGE,
        'total_count': total_count,
    })


@app.route('/ui/post_flags_manual', methods=['POST'])
@auth.auth_required
def post_flags_manual():
    config = reloader.get_config()
    flags = re.findall(config['FLAG_FORMAT'], request.form['text'])

    cur_time = round(time.time())
    rows = [(item, 'Manual', '*', cur_time, FlagStatus.QUEUED.name)
            for item in flags]
    app.logger.info('Inserting flags: %s', rows)
    
    # Use the execute function instead of direct db access
    for row in rows:
        database.execute(
            "INSERT INTO flags (flag, sploit, team, time, status) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (flag) DO NOTHING", 
            row
        )
    return ''

@app.route('/robots.txt', methods=['GET'])
def robots_txt():
    return 'User-agent: *\nDisallow: /'
