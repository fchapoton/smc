"""
HTTP Session Service
"""

import os, subprocess, sys, tempfile, time, urllib2

from sqlalchemy.exc import OperationalError

from flask import Flask, request
app = Flask(__name__)

app_port = 5000 # default

from http_session import post

import frontend_db_model as db

def launch_compute_session(url, id=id, output_url='output'):
    """
    Launch a compute server listening on the given port, and return
    its UNIX process id and absolute path.
    """
    if output_url == 'output':
        output_url = "http://localhost:%s/output/%s"%(app_port, id)
    execpath = tempfile.mkdtemp()
    args = ['python',
            'http_session.py',
            url, 
            'http://localhost:%s/ready/%s'%(app_port, id),
            output_url,
            execpath]
    pid = subprocess.Popen(args).pid
    t = time.time()
    return pid, execpath

def cleanup_sessions():
    S = db.session()
    sessions = S.query(db.Session).all()
    for z in sessions:
        try:
            print "Sending kill -9 signal to %s"%z.pid
            os.kill(z.pid, 9)
            if os.path.exists(z.path):
                shutil.rmtree(z.path)
        except:
            pass
        finally:
            S.delete(z)
            S.commit()
    
@app.route('/new_session')
def new_session():
    # TODO: add ability to specify the output url
    # TODO: we are assuming for now that compute session is on
    # localhost, but it could be on another machine.
    S = db.session()
    if S.query(db.Session).count() == 0:
        id = 0
        port = app_port + 1
    else:
        last_session = S.query(db.Session).order_by(db.Session.id.desc())[0]
        id = last_session.id + 1
        port = int(last_session.url.split(':')[-1]) + 1
        print last_session
    url = 'http://localhost:%s'%port
    print url
    pid, path = launch_compute_session(url=url, id=id)
    if pid == -1:
        return "fail"
    session = db.Session(id, pid, path, url)
    S.add(session)
    S.commit()
    return str(id)

@app.route('/execute/<int:id>', methods=['POST'])
def execute(id):
    if request.method == 'POST':
        if request.form.has_key('code'):
            code = request.form['code']
            print "code = '%s'"%code
            S = db.session()
            # todo: handle invalid id
            session = S.query(db.Session).filter_by(id=id).one()
            print session
            # store code in database.
            cell = db.Cell(session.next_exec_id, session.id, code)
            session.cells.append(cell)
            # increment id for next code execution
            session.next_exec_id += 1
            # commit our *transaction* -- if things go wrong, definitely
            # don't want any of the above db stuff to happen
            S.commit()
            if session.status == 'ready':
                try:
                    session.last_active_exec_id = cell.exec_id
                    post(session.url, {'code':code})  # todo -- timeout?
                    S.commit()  
                    return 'running'
                except urllib2.URLError:
                    # session not alive and responding -- client can decide how to handle
                    return 'dead'
            else:
                # do nothing -- the calculation is enqueued in the database
                # and will get run when the running session tells  us it is
                # no longer running.
                return 'enqueued'

@app.route('/ready/<int:id>')
def ready(id):
    # running compute session has finished whatever it was doing and
    # is now ready.
    S = db.session()
    session = S.query(db.Session).filter_by(id=id).one()
    session.status = 'ready'
    S.commit()
    # if there is anything to compute for this session, start it going.
    if session.last_active_exec_id < session.next_exec_id-1:
        try:
            # get next cell to compute
            cell = S.query(db.Cell).filter_by(exec_id = session.last_active_exec_id + 1,
                                              session_id=session.id).one()
            session.last_active_exec_id = cell.exec_id
            post(session.url, {'code':cell.code})  # todo -- timeout
            S.commit()
            return 'running'
        except urllib2.URLError:
            return 'dead'
    return 'ok'

@app.route('/cells/')
def all_cells():
    # TODO -- JSON and/or proper templates
    S = db.session()
    s = '<pre>'
    for C in S.query(db.Cell).order_by(db.Cell.session_id, db.Cell.exec_id).all():
        s += '<a href="%s">(session %s)</a> '%(C.session_id, C.session_id)
        s += str(C) + '\n\n'
    s += '</pre>'
    return s
    

@app.route('/cells/<int:id>')
def cells(id):
    S = db.session()
    session = S.query(db.Session).filter_by(id=id).one()
    # TODO -- JSON and/or proper templates
    s = '<pre>'
    for C in session.cells:
        s += str(C) + '\n\n'
    s += '</pre>'
    return s
    
@app.route('/interrupt/<int:id>')
def interrupt(id):
    return ''

@app.route('/status/<int:id>')
def status(id):
    return ''

@app.route('/put/<int:id>/<path>', methods=['POST'])
def put(id, path):
    return ''

@app.route('/get/<int:id>/<path>')
def get(id, path):
    return ''

@app.route('/delete/<int:id>/<path>')
def delete(id, path):
    return ''

@app.route('/files/<int:id>')
def files(id):
    return ''

@app.route('/output/<int:id>', methods=['POST'])
def output(id):
    if request.method == 'POST':
        print request.form
        S = db.session()
        m = request.form
        exec_id = m['exec_id']
        cell = S.query(db.Cell).filter_by(exec_id=exec_id, session_id=id).one()
        msg = db.OutputMsg(number=len(cell.output), exec_id=exec_id, session_id=id)
        if 'done' in m:
            msg.done = m['done']
        if 'output' in m:
            msg.output = m['output']
        if 'modified_files' in m:
            msg.modified_files = m['modified_files']
        cell.output.append(msg)
        S.commit()
        return 'ok'
    return 'error'


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print "Usage: %s port"%sys.argv[0]
        sys.exit(1)

    db.create()
    cleanup_sessions()
    app_port = int(sys.argv[1])
    app.run(debug=True, port=app_port)
    
    # TODO: this is wrong below with the try/except, and
    # has something to do with how flask is threaded, maybe.
    try:
        cleanup_sessions()
    except:
        pass
    
