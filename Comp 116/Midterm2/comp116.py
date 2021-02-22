'''Comp116 support module with tools for downloading assignments, lecture notes, and exams
and submitting assignments and exams.

Gary Bishop Fall 2017
'''

import urllib
import os
import os.path as osp
import json
import time
import hashlib
import pickle
import io
import random
import getpass
import inspect
import socket
from datetime import datetime

import matplotlib
import pylab # for side effects on matplotlib
import numpy as np

Site = 'https://wwwx.cs.unc.edu/Courses/comp116-f17/'

##############################
#
# functions for fetching files
#
##############################

ATTEMPTS = 10

def fileHash(filename):
    '''Compute the checksum to be sure the file is what we expect'''
    BLOCKSIZE = 65536
    hasher = hashlib.sha1()
    with open(filename, 'rb') as fp:
        buf = fp.read(BLOCKSIZE)
        while len(buf) > 0:
            hasher.update(buf)
            buf = fp.read(BLOCKSIZE)
    return hasher.hexdigest()

def fetchFile(url, filename, check, token):
    '''Download files to the student's working directory'''
    # make sure the destination folder (if any) exists
    dirname = osp.dirname(filename)
    if dirname and not osp.exists(dirname):
        try:
            os.makedirs(dirname)
        except:
            print('making folder for {} failed'.format(filename))
            return False

    message = ''
    for i in range(ATTEMPTS):
        try:
            filename, headers = urllib.request.urlretrieve(url + '?token=' + token, filename)
            if not check or fileHash(filename) == check:
                break
            else:
                print('checksum')
                message = 'File checksum not correct'
            
        except urllib.error.HTTPError as he:
            if he.code == 401:
                print('Error invalid token')
                return False
            else:
                print('httperror', he.code)
                message = 'HTTP Error {}'.format(he.code)

        # pause before trying again
        time.sleep(0.1 + random.random())

    else:
        print('Too many attempts to fetch file, failing')
        print(message)
        return False

    return True

def fetchAllFiles(siteURL, listname, token):
    '''Make sure the student has all the files listed'''
    listURL = urllib.parse.urljoin(siteURL, listname)
    fp = None
    message = ''
    for i in range(ATTEMPTS):
        try:
            fp = urllib.request.urlopen(listURL)
            code = fp.getcode()
            if code == 200:
                data = json.loads(fp.read().decode('utf-8'))
                break

            message = 'fetch failed, for %s with code %s' % (listname, code)
            
        except IOError:
            message = 'Cannot connect to server'

        except ValueError:
            message = 'File list appears invalid'

        time.sleep(0.1 + random.random())

    else:
        return -1, message

    # if we get here, we successfully retrieved the filelist
    count = 0
    checkedFiles = data['checkedFiles']
    for filename in checkedFiles:
        fileinfo = checkedFiles[filename]
        check = fileinfo.get('check', None)
        force = fileinfo.get('force', False)
        fileURL = urllib.parse.urljoin(siteURL, 'io/fetch.cgi/' + filename)
        if not osp.exists(filename) or (force and check != fileHash(filename)):
            print('fetching', filename)
            if not fetchFile(fileURL, filename, check, token):
                return -1, 'fetching files failed'
            count += 1

    return count, ''

def fetch2(token, *args):
    r, message = fetchAllFiles(Site, 'media/downloads.json', token)
    if r == 0:
        print('You have all the files that have been released.')
    elif r > 0:
        print('Fetched {} files'.format(r))
        print('Now go back to your Dashboard tab to see any new notebooks.')
    elif password:
        print('Fetch failed. Is the password correct?')
    else:
        print(message)

def fetch(*args):
    import IPython.display as ipd
    html = '''
        <button type="button" id="fetchButton116">Fetch your notebooks</button>
        <pre id="fetchMessages116"></pre>
        <script>
        $('#fetchButton116').on('click', function() {
            var $log = $('#fetchMessages116');
            $log.empty();
            $log.append('Login to fetch your notebooks<br>');
            $.ajax({
                url: 'SITE' + 'io/token/token.cgi',
                dataType: 'jsonp'
            }).done(function(data) {
                $log.empty().append('Fetching notebooks for ' + data.userid + '<br>');
                var notebook = IPython.notebook.notebook_name,
                    uuid = data.token,
                    command = "import comp116; comp116.fetch2('" + uuid + "')",
                    kernel = IPython.notebook.kernel,
                    handler = function (out) {
                        if (out.msg_type == 'stream') {
                            $log.append(out.content.text);
                        } else if(out.msg_type == "error") {
                            $log.append(out.content.ename + ": " + out.content.evalue);
                        } else { // if output is something we haven't thought of
                            $log.append("[out type not implemented]")
                        }
                    };
                kernel.execute(command, { 'iopub' : {'output' : handler}}, {silent:false});
            }).fail(function() {
                $log.append('Login failed');
            });
        });
        </script>
    '''.replace('SITE', Site)
    return ipd.HTML(html)

#############################
#
# functions for submitting assignments
#
#############################

def pushNotebook(name, uuid,
        url = 'io/submit.cgi'):
    '''Upload the notebook to our server'''

    if not name.endswith('.ipynb'):
        fname = name + '.ipynb'
    else:
        fname = name
    try:
        book = open(fname, 'rb').read()
    except IOError:
        raise UserWarning('Notebook %s not found.' % fname)
    check = fileHash(fname)
    try:
        assignment = expected['_assignment']
    except KeyError:
        raise UserWarning('Missing assignment, you must run your notebook before submitting it.')

    data = {
        'filename': name,
        'book': book,
        'token': uuid,
        'assignment': assignment,
        'check': check
    }

    postdata = urllib.parse.urlencode(data)
    postdata = postdata.encode('UTF-8') # data should be bytes
    req = urllib.request.Request(Site + url, postdata)
    # try to post it to the server
    for i in range(10):
        try:
            resp = urllib.request.urlopen(req)
        except urllib.error.URLError:
            raise
            break
        except urllib.error.HTTPError as e:
            print(e)
            raise
        if resp.getcode() == 200:
            break
        time.sleep(0.1 * i)
    else:
        code = resp.getcode()
        msg = resp.read()
        raise UserWarning('upload failed code={} msg="{}"'.format(code, msg))

def showSubmitButton():
    '''Generate code to diplay the submit button in the notebook'''
    import IPython.display as ipd

    html = '''
<p>Click the button below to submit your notebook. Watch for a confirmation message
that your notebook was successfully uploaded. You may submit as often as you wish,
only the last submission will count.</p>
<button id="submitButton116">Submit this notebook</button>
<p id="submitResponse116"></p>
<script>
var site = 'SITE';
$('#submitButton116').on('click', function() {
    var site = 'SITE',
        $sresp = $('#submitResponse116'),
        button = $('#submitButton116');
    button.prop('disabled', true);
    // wait until save is complete before pushing the notebook
    $([IPython.events]).one('notebook_saved.Notebook', function() {
        // get the token by logging in
        $sresp.html('logging in');
        $.ajax({
            url: site + 'io/token/token.cgi',
            dataType: 'jsonp'
        }).done(function(data) {
            var notebook = IPython.notebook.notebook_name,
                uuid = data.token,
                command = "comp116.pushNotebook('" + notebook + "', '" + uuid + "')",
                kernel = IPython.notebook.kernel,
                handler = function (out) {
                    $('#comp116-stop-message').show();
                    if (out.content.status == "ok") {
                        $sresp.html("Successfully submitted " + notebook);
                        $('#comp116-stop-message').hide();
                    } else if(out.content.status == "error") {
                        $sresp.html(out.content.ename + ": " + out.content.evalue);
                    } else { // if output is something we haven't thought of
                        $sresp.html("[out type not implemented]")
                    }
                    button.prop('disabled', false);
                };
            $sresp.html('Submitting');
            kernel.execute(command, {shell: { reply: handler }});
        }).fail(function() {
            $sresp.html('Login failed');
            button.prop('disabled', false);
        });
    });
    // trigger the save
    $sresp.html('Saving');
    IPython.notebook.save_notebook();
});'''.replace('SITE', Site)
    return ipd.HTML(html)

##################################################
#
# functions for checking student answers
#
##################################################

def check_function(tag, func, *args, **kwargs):
    if not callable(func):
        print(tag, 'not a function')
        return
    try:
        no_globals(func)
    except AssertionError:
        print(tag, 'incorrect use of global variables')
        return
    try:
        result = func(*args)
    except:
        print(tag, 'function produces an error')
        raise

    check(tag, result, **kwargs)

def check_array(tag, given, ev, extra):
    '''Compare arrays and array-like things'''
    rtol = 10.0 ** -extra.get('precision', 5)
    if not isinstance(given, np.ndarray):
        try:
            given = np.array(given)
        except:
            print(tag, 'incorrect type, expected array-like')
            return 0.0

    if given.shape != ev.shape:
        print(tag, 'incorrect shape')
        print('  expected', ev.shape, 'got', given.shape)
        return 0.0

    if issubclass(ev.dtype.type, np.number):
        if issubclass(given.dtype.type, np.number):
            if not np.allclose(given, ev, rtol=rtol):
                print(tag, 'incorrect values in array')
                return 0.0
        else:
            print(tag, 'incorrect array type', given.dtype.type)
            print('  expected', ev.dtype.type)
            return 0.0

    else:
        try:
            if not np.all(ev == given):
                print(tag, 'incorrect values in array')
                return 0.0
        except:
            print(tag, 'incorrect array value')
            return 0.0

    return 1.0

def normalize_y(yh):
    '''normalize bar graph y with a row of minimums and a row of maximums'''
    y0 = yh[0]
    y1 = y0 + yh[1]
    ys = np.array([y0, y1])
    ymin = np.min(ys, axis=0)
    ymax = np.max(ys, axis=0)
    return np.array([ymin, ymax])

def check_bars(tag, given, expected, rtol=1e-6, atol=1e-8):
    '''Compare bar graphs'''
    if given.shape[-1] != expected.shape[-1]:
        print(tag, 'Wrong number of bars')
        return 0
    if not np.allclose(given[0], expected[0], rtol=rtol, atol=atol):
        print(tag, 'X values incorrect')
        return 0
    gy = normalize_y(given[1:])
    ey = normalize_y(expected[1:])
    if not np.allclose(gy, ey, rtol=rtol, atol=atol):
        print(tag, 'Y values incorrect')
        return 0
    return 1

def check_figure(tag, given, ev, extra):
    '''Compare a few features of figures'''
    rtol = extra.get('relative_tolerance', 1e-5)
    atol = extra.get('absolute_tolerance', 1e-8)
    given = figureState(given)
    LabelScore = 0.0
    LabelWeight = 0.0
    for attr in ['title', 'xlabel', 'ylabel']:
        if ev[attr]:
            LabelWeight += 1
            if ev[attr] != given[attr]:
                print(tag, attr, 'incorrect')
                print('  expected', ev[attr])
            else:
                LabelScore += 1
    if LabelWeight > 0:
        LabelScore /= LabelWeight
        LabelWeight = 1.0

    # compare line graphs
    LineWeight = 0.0
    nlines = len(ev['lines'])
    LOK = np.zeros(nlines)
    if nlines:
        LineWeight = 1.0
        glines = len(given['lines'])
        for i in range(glines):
            gline = given['lines'][i]
            for j in range(nlines):
                if not LOK[j]:
                    eline = ev['lines'][j]
                    LOK[j] = (len(eline[0]) == len(gline[0]) and
                        len(eline[1]) == len(gline[1]) and
                        np.allclose(eline[0], gline[0], rtol=rtol, atol=atol) and
                        np.allclose(eline[1], gline[1], rtol=rtol, atol=atol))
                    if LOK[j]:
                        break

        LineScore = np.mean(LOK)

        if LineScore == 0:
            print(tag, 'values of plotted lines incorrect')
        elif LineScore < 1.0:
            print(tag, 'values of some lines incorrect')
    else:
        LineScore = 0

    if LineScore > 0 and glines > nlines:
        print(tag, 'too many lines')
        LineScore *= float(nlines) / glines

    # compare bar charts
    BarWeight = 0.0
    nbars = ev['bars'].shape[1]
    if nbars:
        BarWeight = 1.0
        BarScore = check_bars(tag, given['bars'], ev['bars'], rtol=rtol, atol=atol)

    else:
        BarScore = 0

    Score = (LabelScore + LineScore + BarScore) / float(LabelWeight + LineWeight + BarWeight)
    return Score

def check_float(tag, given, ev, extra):
    '''Compare floats for approximate equality'''
    rtol = 10.0 ** -extra.get('precision', 5)
    if not isinstance(given, (float, int)):
        print(tag, 'incorrect type')
        print(' expected float')
        return 0.0
    OK = np.allclose(given, ev, rtol=rtol)
    if not OK:
        print(tag, 'incorrect')
        print('  expected', ev)
    return float(OK)

try:
    from grading import record_grade
except ImportError:
    def record_grade(expected):
        pass

try:
    from solution import start, check, report
except ImportError:

    # contains the expected answers
    expected = {}


    def test_online(host='8.8.8.8', port=53, timeout=1):
        '''Test to see if the user is online'''
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except Exception as ex:
            return False

    def start(assignment):
        '''Initialize expected values for checking a student submission'''
        pname = assignment + '.pickle'
        expected.update(pickle.load(open(pname, 'rb')))
        if expected.get('_exam', False) and time.time() - osp.getmtime(pname) < 3 * 60 * 60:
            expected['_monitor'] = True
        return check, report

    def check(tag, value, *args, **kwargs):
        '''Provide feedback on a single value'''

        if expected.get('_monitor') and test_online():
            import IPython.display as ipd
            ipd.display(ipd.HTML('''
<p style="background:pink;height:8em;display:flex;align-items:center">
You appear to be online.  Disable wireless before continuing. %s</p>''' % datetime.now().isoformat())) 

        assert tag in expected
        e = expected[tag]
            
        dv = describe_answer(value)
        score = 1.0
        
        #if e['description'] != dv:
        #    print(tag, 'incorrect type')
        #    print('your answer type is', dv)
        #    print('expected type is', e['description'])
        #    score = 0.0
            
        if callable(value):
            try:
                no_globals(value)
            except AssertionError:
                score = 0.0
                print('incorrect use of global variables')
            else:
                e['correct'] = 1.0
                print(tag, 'function signature appears correct')
                value = value(*args)
                return check(tag+'-result', value, **kwargs)
            
        elif 'hash' in e:
            hv = hash_answer(value, kwargs.get('precision', 5))
            if hv != e['hash']:
                score = 0.0
                print(tag, 'incorrect')
                
        else:
            ev = e['value']
            extra = e['extra']

            if isinstance(ev, np.ndarray) or (isinstance(value, np.ndarray) and isinstance(ev, list)):
                score = check_array(tag, value, np.array(ev), extra)

            elif isinstance(ev, dict) and 'FigureState' in ev:
                score = check_figure(tag, value, ev, extra)

            elif isinstance(ev, float):
                score = check_float(tag, value, ev, extra)

            elif np.all(value == ev):
                pass

            else:
                print(tag, 'incorrect')
                print('  expected', ev)
                score = 0.0

        if score == 1.0:
            print(tag, 'appears correct')

        elif score > 0:
            print(tag, 'partially correct')

        e['correct'] = score
        
    def tagSort(tags):
        return sorted(tags,
            key=lambda tag: ''.join([ s.isdigit() and '%02d'%int(s) or s
                              for s in re.findall(r'\d+|\D+', tag)
                              ]))

    def report(author, extra):
        '''Summarize the student's performance'''
        expected['_score'] = 0.0
        correct = 0
        problems = 0
        answered = 0
        points = 0
        max_points = 0
        for tag in tagSort(expected.keys()):
            if tag.startswith('_'):
                continue
            problems += 1
            c = expected[tag]['correct']

            if c > 0:
                correct += c
                points += expected[tag]['points'] * c
                if c < 1:
                    print(tag, 'partially incorrect')
                else:
                    print(tag, 'appears correct')
            else:
                print(tag, 'incorrect')
            max_points += expected[tag]['points']
        if '_author' in expected and author == expected['_author']:
            print('You must fill in your onyen into the author variable.')
            return
        print("Report for", author)

        if '_exam' in expected and expected['_exam']:
            if not extra:
                print('You must type your name as the value of the pledge variable.')
                return
            else:
                print("  Pledged on my honor:", extra)
                print("   ", getpass.getuser())

        elif '_collaborators' in expected and extra == expected['_collaborators']:
            print('You must fill in the collaborators variable')
            return
        else:
            print("  Collaborators:", extra)
        print("  {} of {} possibly correct for up to {} of {} points".format(correct, problems, points, max_points))
        expected['_score'] = points
        
        record_grade(expected)

        return showSubmitButton()

def submit(ws):
    expected['_assignment'] = ws
    return showSubmitButton()
    
def no_globals(*funcs):
    '''Warn about global variables in functions, a common source of problems'''
    import inspect
    NoGlobalVars = True
    for func in funcs:
        for gname, gvalue in inspect.getclosurevars(func).globals.items():
            if not inspect.ismodule(gvalue) and not inspect.isfunction(gvalue):
                print('Warning: You appear to be using global variable "{}" in function "{}"'
                    .format(gname, func.__name__))
                NoGlobalVars = False
    assert NoGlobalVars, 'Use only parameters and local variables in your functions'

def figureState(f):
    '''Extract interesting bits of the state out of a figure'''
    s = {
        'FigureState':True,
        'title': '',
        'xlabel': '',
        'ylabel': '',
        'lines': [],
        'bars' : np.zeros((3, 0))
    }
    try:
        axis = f.axes[0]
        s['title'] = axis.title.get_text()
        s['xlabel'] = axis.xaxis.label.get_text()
        s['ylabel'] = axis.yaxis.label.get_text()
        s['lines'] = [(line.get_xdata(), line.get_ydata())
                      for line in axis.lines]
        xbars = [p.get_x() for p in axis.patches]
        ybars = [p.get_y() for p in axis.patches]
        hbars = [p.get_height() for p in axis.patches]
        s['bars'] = np.array([xbars, ybars, hbars])
    except:
        pass
    return s

from collections import OrderedDict
import re

def describe_answer(o):
    '''describe the type of an object in English'''
    def wrap(d):
        '''Enclose description in parenthesis if it contains comma or and.'''
        if ', ' in d or ' and ' in d:
            return '(' + d + ')'
        else:
            return d

    def and_list(items):
        '''comma separated list with and at the end'''
        if len(items) <= 2:
            return " and ".join(items)
        return ", ".join(items[ : -1]) + ", and " + items[-1]

    def describe_sequence(o, typ, memo):
        '''describe a list or tuple'''
        if len(o) == 0:
            return 'empty ' + typ
        if id(o) in memo:
            return '[...]'
        memo.add(id(o))
        et = [ wrap(describe_any(e, memo)) for e in o ]
        uet = list(OrderedDict.fromkeys(et))
        if len(uet) == 1:
            et = '{} {}'.format(len(et), uet[0])
        else:
            et = and_list(et)
        return typ + ' of ' + et
    
    def describe_dict(o, memo):
        if len(o) == 0:
            return 'empty dict'
        if id(o) in memo:
            return '{...}'
        memo.add(id(o))
        it = [ (describe_any(k, memo) + ':' + wrap(describe_any(v, memo))) for k,v in o.items() ]
        uit = list(OrderedDict.fromkeys(it))
        if len(uit) == 1:
            it = '{} {}'.format(len(o), uit[0])
        else:
            it = and_list(it)
        return 'dictionary of {}'.format(it)
    
    def describe_array(a):
        '''Describe a numpy array in English'''
        if issubclass(a.dtype.type, np.integer):
            t = 'integer'
        elif issubclass(a.dtype.type, np.float):
            t = 'float'
        elif issubclass(a.dtype.type, np.complex):
            t = 'complex'
        elif issubclass(a.dtype.type, np.bool_):
            t = 'boolean'
        else:
            t = str(a.dtype)
        s = ' x '.join(str(i) for i in a.shape)
        if s == '0':
            return 'empty array of ' + t
        return 'array of {} {}'.format(s, t)

    def describe_plot(o):
        '''describe a plot'''
        o = figureState(o)
        terms = []
        nlines = len(o['lines'])
        if nlines > 0:
            terms.append('{} line{}'.format(nlines, "s"[nlines==1:]))
        nbars = o['bars'].shape[-1]
        if nbars > 0:
            terms.append('{} bar{}'.format(nbars, "s"[nbars==1:]))
        for t in ['title', 'xlabel', 'ylabel']:
            if o[t]:
                terms.append(t)
        if len(terms) == 0:
            return 'empty plot'
        else:
            return 'plot with ' + and_list(terms)

    def describe_function(f):
        return 'function with %d parameter' % len(inspect.signature(f).parameters)
        
    def describe_any(o, memo):
        if isinstance(o, str):
            return 'string'
        if isinstance(o, (int, np.integer)):
            return 'integer'
        if isinstance(o, (float, np.floating)):
            return 'float'
        if isinstance(o, (bool, np.bool_)):
            return 'boolean'
        if o is None:
            return 'None'
        if isinstance(o, np.ndarray):
            return describe_array(o)
        if isinstance(o, list):
            return describe_sequence(o, 'list', memo)
        if isinstance(o, tuple):
            return describe_sequence(o, 'tuple', memo)
        if isinstance(o, dict):
            return describe_dict(o, memo)
        if isinstance(o, matplotlib.figure.Figure):
            return describe_plot(o)
        if callable(o):
            return describe_function(o)
        return str(type(o))
    
    desc = describe_any(o, set())
    def pluralize(m):
        n = int(m.group(1))
        w = m.group(3)
        if n != 1:
            if w == 'dictionary':
                w = 'dictionaries'
            else:
                w = w + 's'
        return m.group(1) + ' ' + m.group(2) + w
    desc = re.sub(r'(\d+) (\(?)(tuple|list|dictionary|integer|float|boolean|plot|parameter)', pluralize, desc)
    return desc

import hashlib

def hash_answer(o, precision=5):
    '''return a hash to represent the answer in equality tests'''
    def str_answer(o, memo):
        '''compute a hash for an answer'''
        if id(o) in memo:
            return '...'
        memo.add(id(o))
        if isinstance(o, np.ndarray):
            s = 'array' + np.array2string(o, precision=precision).replace('\n', '')
        elif isinstance(o, matplotlib.figure.Figure):
            s = 'figure' + str_answer(sorted(figureState(o).items()), memo)
        elif isinstance(o, float):
            s = 'float' + format(o, '.{}e'.format(precision))
        elif isinstance(o, (list, tuple)):
            s = str(type(o).__name__) + '(' + ','.join([str_answer(i, memo) for i in o]) + ')'
        elif isinstance(o, dict):
            s = 'dict' + str_answer(sorted(o.items()), memo)
        else:
            s = str(o)
        return s

    sa = str_answer(o, set())

    return hashlib.md5(str_answer(o, set()).encode('utf-8')).hexdigest()

