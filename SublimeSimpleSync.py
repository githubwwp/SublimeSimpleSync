#
# Sublime Text 2/3 SimpleSync plugin
#
# based on https://github.com/tnhu/SimpleSync
#

import os
# import sys
import platform
import subprocess
import threading
# import re
import sublime
import sublime_plugin
import zipfile
# print(os.path.join(sublime.packages_path(), 'Default'))

# Caches
#__name__ # ST3 bug with __name__
BASE_PATH = os.path.abspath(os.path.dirname(__file__))
PACKAGE_NAME = 'SublimeSimpleSync'
PACKAGE_SETTINGS = PACKAGE_NAME + '.sublime-settings'
OS = platform.system()
# print('*********', os.name, sys.platform, OS)
IS_GTE_ST3 = int(sublime.version()[0]) >= 3


class syncCommand():

    # get settings
    def getSetting(self):
        return sublime.load_settings(PACKAGE_SETTINGS)

    # Get file path
    def getPath(self):
        if self.window.active_view():
            return self.window.active_view().file_name()
        else:
            # sublime.error_message(PACKAGE_NAME + ': No file_name')
            self.syncPastePath()
            return False

    # Get sync item(s) for a file
    def getSyncItem(self, localFile):
        ret = []
        # print(localFile, self.rules)
        for item in self.rules:
            # print(localFile.startswith(item['local']), localFile, item['local'])
            if localFile.startswith(item['local']):
                ret += [item]
        return ret

    # support multiple rules
    def syncFile(self, localFile):
        syncItems = self.getSyncItem(localFile)
        # print('+++ syncCommand: ', syncItems)
        if (len(syncItems) > 0):
            for item in syncItems:
                # fix path(/)
                relPath = localFile.replace(item['local'], '')
                remoteFile = item['remote'] + '/' + relPath
                # print('********', remoteFile)
                if (item['type'] == 'ssh'):
                    password = item['password'] if 'password' in item else ''
                    ScpCopier(item['host'], item['username'], password, localFile, remoteFile, port=item['port'], relPath=relPath).start()
                elif (item['type'] == 'local'):
                    LocalCopier(localFile, remoteFile).start()

    def syncPastePath(self):
        file_path = ''
        def on_done(file_path):
            # print(file_path)
            if not file_path: return
            self.syncFile(file_path)
        self.window.show_input_panel('[%s] Copy and paste local file path :' % (PACKAGE_NAME), file_path, on_done, None, None)

# show_input_panel and paste local file path
# { "keys": ["alt+shift+s"], "command": "sublime_simple_sync_path"},
class SublimeSimpleSyncPathCommand(sublime_plugin.WindowCommand, syncCommand):
    def run(self):
        settings = self.getSetting()
        self.rules = settings.get('rules')
        self.syncPastePath()

# { "keys": ["alt+s"], "command": "sublime_simple_sync"},
class SublimeSimpleSyncCommand(sublime_plugin.WindowCommand, syncCommand):
    def run(self):
        # for x in self.window.views(): print(x.file_name())
        settings = self.getSetting()
        self.rules = settings.get('rules')
        # auto save
        self.window.run_command('save')

        localFile = self.getPath()
        # print('********', localFile)
        if localFile is not False:
            self.syncFile(localFile)


# auto run, sublime_plugin.EventListener
class SimpleSync(sublime_plugin.EventListener, syncCommand):
    # on save
    def on_post_save(self, view):
        settings = self.getSetting()
        # print('********', settings)

        config = settings.get('config', [])
        autoSycn = config['autoSync'] if 'autoSync' in config else False
        localFile = view.file_name()
        # print('********', localFile)

        if autoSycn:
            self.rules = settings.get('rules')
            self.syncFile(localFile)

# command = Command("echo 'Process started'; sleep 2; echo 'Process finished'")
# command.run(timeout=3)
class Command(object):
    def __init__(self, cmd):
        self.cmd = cmd
        self.process = None
        self.msg = None

    def run(self, timeout=10):
        def target():
            # print ('Thread started')
            self.process = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
            (stdout, stderr) = self.process.communicate()
            # print ('Thread finished')
            # print(stdout, stderr)
            #self.process.stdout.read().decode('utf-8')
            self.msg = stdout.decode('utf-8')

        thread = threading.Thread(target=target)
        thread.start()

        thread.join(timeout)
        if thread.is_alive():
            # print ('Terminating process')
            self.process.terminate() # kill proc
            thread.join()
        # print (self.process.returncode)

# ScpCopier does actual copying using threading to avoid UI blocking
class ScpCopier(threading.Thread, syncCommand):
    def __init__(self, host, username, password, localFile, remoteFile, port=22, relPath=''):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.localFile = localFile
        self.remoteFile = remoteFile
        self.relPath = relPath
        # print('relative path:', relPath)

        settings = self.getSetting()
        config = settings.get('config')
        self.debug = config['debug'] if 'debug' in config else False
        self.timeout = config['timeout'] if 'timeout' in config else 10

        threading.Thread.__init__(self)

    def run(self):
        packageDir = os.path.join(sublime.packages_path(), PACKAGE_NAME)
        # for windows
        self.remoteFile = self.remoteFile.replace('\\', '/').replace('//', '/')
        remote = self.username + '@' + self.host + ':' + self.remoteFile

        # print(PACKAGE_NAME , self.localFile, ' -> ', self.remoteFile)

        pw = []
        ext = ['-r', '-C', '-P', str(self.port), self.localFile, remote]

        if OS == 'Windows':
            # cmd = os.environ['SYSTEMROOT'] + '\\System32\\cmd.exe'

            scp = os.path.join(packageDir, 'pscp.exe')
            args = [scp]
                # args = [scp, "-v"] # show message

            # run with .bat
            # scp = os.path.join(packageDir, 'sync.bat')
            # args = [scp]
            # pw.extend(ext)
            # pw = ' '.join(pw)
            # args.extend([packageDir, pw])
            if self.password:
                pw = ['-pw', self.password]
            args.extend(pw)
        else:
            args = ['scp']

        args.extend(ext)
        cmd = ' '.join(args)
        print(PACKAGE_NAME + ': ' + cmd)

        if OS != 'Windows' and self.password: # use password, ignore authorized_keys
            cmd = r"""
            expect -c "
            set timeout {timeout};
            spawn {cmd};
            expect *password* {{ send \"{password}\r\" }};
            expect *\r
            expect "100%"
            expect eof"
            """.format(cmd=cmd, password=self.password, timeout=self.timeout)
            # print(args)

        self.i = 1
        self.done = False

        def show_loading():
            # print(self.i)
            if self.i % 2 == 0:
                s = 0
                e = 3
            else:
                s = 3
                e = 0
            if not self.done:
                sublime.status_message('%s [%s=%s]' % (PACKAGE_NAME, ' ' * s, ' ' * e))
                sublime.set_timeout(show_loading, 500)
                self.i += 1
        show_loading()

        # return
        try:
            command = Command(cmd)
            command.run(timeout=self.timeout)

            def status_message(msg):
                sublime.status_message('%s: %s' % (PACKAGE_NAME, msg))

            def sync_folder():
                self.localFile = os.path.dirname(self.localFile)
                self.remoteFile = os.path.dirname(os.path.dirname(self.remoteFile))
                # print(self.localFile, ',', self.remoteFile)
                ScpCopier(self.host, self.username, self.password, self.localFile, self.remoteFile, self.port).start()

            def show_msg(msg):
                if msg.find('no such file or directory') != -1:
                    if sublime.ok_cancel_dialog('No such file or directory\n' + self.relPath + '\n' + '* Do you want to sync the parent folder?'):
                        sync_folder()
                elif msg.find('Host key verification failed') != -1:
                # else:
                    msg = 'Please generate SSH public-key and run: \n'
                    msg += 'ssh -p ' + self.port + ' ' + self.username + '@' + self.host + " 'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys' < ~/.ssh/id_rsa.pub \n"
                    status_message('Sync failed')
                    sublime.message_dialog(msg)
                elif msg.find('Permission denied (publickey,password)') != -1: # authorized faild
                    msg = 'Scp auth faild. Please check your sshd_config, and enable AuthorizedKeysFile!'
                    status_message('Sync failed')
                    sublime.message_dialog(msg)
                else:
                    if msg:
                        if msg.find('100%') != -1:
                            status_message('Completed!')
                        elif msg.find('s password:') != -1:
                            msg = 'Please enlarge the ["config"]["timeout"] in %s settings (Default: 10)' % (PACKAGE_NAME)
                            status_message('Sync failed')
                            sublime.message_dialog(msg)
                        else:
                            sublime.status_message('Sync failed')
                            sublime.message_dialog(msg)
                    else:
                        status_message('Completed!')
            if self.debug:
                print(command.msg, command.process.returncode)
            show_msg(command.msg)

        except Exception as exception:
            # Alert "SimpleSync: No file_name", if the file size is zero.
            # print(exception);
            sublime.error_message(PACKAGE_NAME + ': ' + exception)
        self.done = True


# LocalCopier does local copying using threading to avoid UI blocking
class LocalCopier(threading.Thread, syncCommand):
    def __init__(self, localFile, remoteFile):
        self.localFile = localFile
        self.remoteFile = remoteFile

        # settings = self.getSetting()
        # config = settings.get("config")
        # self.debug = config['debug'] if "debug" in config else False
        threading.Thread.__init__(self)

    def run(self):
        # print(PACKAGE_NAME, self.localFile, ' -> ', self.remoteFile)

        if OS == 'Windows':
            # subprocess.call(args)
            # cmd = os.environ['SYSTEMROOT'] + '\\System32\\cmd.exe'
            # args = [cmd, '/c', 'copy', '/y']

            # subprocess.call(args, shell=True)
            # args = ['copy', '/y']
            args = ['xcopy', '/y', '/e', '/h']

            # folder path
            # print(os.path.split(self.remoteFile)[0])
            # print(os.path.dirname(self.remoteFile))
            # print(re.sub(r'\\[^\\]*$', '', self.remoteFile))

            # print('*********', self.remoteFile)
            # replace C:\test/\test\ -> C:\test\test\
            self.remoteFile = self.remoteFile.replace('/\\', '\\')
            # replace /path/file.ext -> /path
            self.remoteFile = os.path.dirname(self.remoteFile) + '\\'
            # print('*********', self.remoteFile)
        else:
            args = ['cp']
        args.extend([self.localFile, self.remoteFile])

        print(PACKAGE_NAME + ': ' + ' '.join(args))
        # return
        try:
            retcode = subprocess.call(args, shell=True)
            print(retcode)

        except Exception as exception:
            # print(exception);
            sublime.error_message(PACKAGE_NAME + ': ' + str(exception))


def plugin_loaded():  # for ST3 >= 3016
    PACKAGES_PATH = sublime.packages_path()
    TARGET_PATH = os.path.join(PACKAGES_PATH, PACKAGE_NAME)
    # print(TARGET_PATH);
    # first run
    if not os.path.isdir(TARGET_PATH):
        os.makedirs(TARGET_PATH)
        # copy files
        file_list = [
            'Main.sublime-menu', 'pscp.exe',
            'SublimeSimpleSync.py',
            'README.md',
            'SublimeSimpleSync.sublime-settings',
            'sync.bat'
        ]
        try:
            extract_zip_resource(BASE_PATH, file_list, TARGET_PATH)
        except Exception as e:
            print(e)

if not IS_GTE_ST3:
    sublime.set_timeout(plugin_loaded, 0)

def extract_zip_resource(path_to_zip, file_list, extract_dir=None):
    if extract_dir is None:
        return
    # print(extract_dir)
    if os.path.exists(path_to_zip):
        z = zipfile.ZipFile(path_to_zip, 'r')
        for f in z.namelist():
            # if f.endswith('.tmpl'):
            if f in file_list:
                # print(f)
                z.extract(f, extract_dir)
        z.close()
