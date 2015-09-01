#!/usr/bin/env python
# vim: set ts=8 sw=4 sts=4 et ai:
# pycoredump -- Walter Doekes, OSSO B.V. 2015
from __future__ import absolute_import, print_function
from subprocess import Popen, PIPE


def hexint(value):
    if value.startswith('0x'):
        return int(value[2:], 16)
    raise ValueError('Expected 0xHEX integer, got {}'.format(value))


class ReadUntilMixin(object):
    """
    Implements read_until(). Does not require select/poll/push-back
    functionality because it reads very slowly (bytewise) when it
    reaches what it's supposed to find.
    """
    def __init__(self, readfunc, **kwargs):
        super(ReadUntilMixin, self).__init__(**kwargs)
        self.__readfunc = readfunc

    def read_until(self, what):
        ret = []

        prev, both = '', ''
        while True:
            for i in range(len(what) - 1, -1, -1):
                if both.endswith(what[0:i]):
                    break
            bufsize = len(what) - i
            next_ = self.read(bufsize)
            both = prev + next_
            try:
                index = both.index(what)
            except ValueError:
                ret.append(prev)
                prev = next_
            else:
                assert index + len(what) == len(both)
                ret.append(both)
                break
        return ''.join(ret)


class SubprocessIO(ReadUntilMixin):
    """
    Implements open()/read()/write()/close() and the with-statement.

    You should implement command() that returns the output of a command.
    """
    def __init__(self, procargs, **kwargs):
        super(SubprocessIO, self).__init__(readfunc=self.read, **kwargs)
        self.__procargs = procargs
        self.__procfp = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, type, value, tb):
        self.close()

    def open(self):
        assert not self.__procfp
        self.__devnull = open('/dev/null', 'w')
        self.__procfp = Popen(
            self.__procargs, stdin=PIPE, stdout=PIPE, stderr=self.__devnull,
            env={'TERM': 'dumb'},
            preexec_fn=None, close_fds=True)  # os.setsid() on preexec?

    def read(self, size):
        return self.__procfp.stdout.read(size).decode('ascii')

    def write(self, what):
        self.__procfp.stdin.write(what.encode('ascii'))
        self.__procfp.stdin.flush()

    def close(self):
        assert self.__procfp
        self.__procfp.stdin.close()   # needed?
        self.__procfp.stdout.close()  # needed?

        if self.__procfp.poll() is None:
            self.__procfp.kill()
        self.returncode = self.__procfp.wait()
        assert self.returncode is not None
        del self.__procfp

        self.__devnull.close()
        del self.__devnull


class GdbMultiLine(object):
    @classmethod
    def parse_gdb(cls, gdb, data):
        def feed(data):
            data = data.split('\n')
            prevlines = []
            for line in data:
                if not line.startswith('   '):
                    yield prevlines
                    prevlines = []
                prevlines.append(line)
            yield prevlines

        ret = []
        for rows in feed(data):
            try:
                instance = cls(gdb, ' '.join(rows))
            except ValueError:
                pass
            else:
                ret.append(instance)
        return ret


class GdbBacktraceMixin(object):
    class GdbBacktrace(object):
        class GdbFrame(GdbMultiLine):
            def __init__(self, gdb, line):
                self.gdb = gdb
                cols = line.split()
                if not cols:
                    raise ValueError(line)
                self.frameno = int(cols[0][1:])
                if cols[2] == 'in':
                    self.funcaddr = hexint(cols[1])
                    cols = cols[3:]
                else:
                    self.funcaddr = 0
                    cols = cols[1:]
                self.func = cols.pop(0)
                self.file = cols.pop()
                if not cols:
                    raise ValueError(line)
                where = cols.pop()
                assert where in ('at', 'from')  # from for libs
                self.funcargs = ' '.join(cols[1:])

            def __repr__(self):
                return '<GdbFrame(no={}, func={}, file={}>'.format(
                    self.frameno, self.func, self.file)

        def __init__(self, gdb, data):
            self.gdb = gdb
            self.frames = self.GdbFrame.parse_gdb(gdb, data)
            assert [(self.frames[i + 1].frameno - self.frames[i].frameno) == 1
                    for i in range(len(self.frames) - 1)]

        def __repr__(self):
            return '<GdbBacktrace(\n {}\n)>'.format(
                '\n '.join(repr(i) for i in self.frames))

    def backtrace(self):
        ret = self.command('bt')
        return self.GdbBacktrace(self, ret)


class Gdb(GdbBacktraceMixin, SubprocessIO):
    """
    Implements command().
    """
    def __init__(self, program, corefile):
        super(Gdb, self).__init__(procargs=(
            'gdb', '-quiet', program, corefile))
        self.__sentinel = '--SENTINEL--'

    def open(self):
        super(Gdb, self).open()
        self._skip_intro()

    def command(self, command):
        self.write(command + '\n')
        ret = self._read_until_sentinel()
        assert ret.startswith('(gdb) ')
        return ret[6:]

    def expression(self, expression):
        ret = self.command('print {}'.format(expression))
        ret = ret.split(' = ', 1)[1]
        ret = ret.replace('\n', ' ')
        return ret

    def _skip_intro(self):
        return self._read_until_sentinel()

    def _read_until_sentinel(self):
        self.write('print "{}"\n'.format(self.__sentinel))
        expected = ' = "{}"\n'.format(self.__sentinel)
        ret = self.read_until(expected)
        # The sentinel looks like '(gdb) $xxx = "--SENTINEL--"'.
        # Remove it from the tail.
        pos = ret.rindex('\n(gdb) $')
        return ret[0:pos]


class GdbWithThreads(Gdb):
    def __init__(self, **kwargs):
        super(GdbWithThreads, self).__init__(**kwargs)
        self.__thno = None

    def thread(self, thno):
        if self.__thno != thno:
            self.command('thread {}'.format(thno))
            self.__thno = thno

    @property
    def threads(self):
        if not hasattr(self, '_threads'):
            ret = self.command('info threads')
            self._threads = GdbThread.parse_gdb(self, ret)
        return self._threads

    def thread_by_procid(self, procid):
        return [i for i in self.threads if i.procid == procid][0]


class GdbThread(GdbMultiLine):
    class PthMutex(object):
        def __init__(self, gdb, addr, value):
            # {__data = {__lock = 2, __count = 1, __owner = 39090,
            #  __nusers = 1, __kind = 1, __spins = 0, __list =
            #  {__prev = 0x0, __next = 0x0}}, __size = "\002...",
            #  '\000' <repeats 22 times>, __align = 4294967298}
            self.gdb = gdb
            self.addr = addr
            self.value = value
            pre, post = value.split(' __owner = ', 1)
            try:
                num, rest = post.split(',', 1)
            except ValueError:
                num, rest = post.split('}', 1)
            self.held_by_procid = int(num)

        @property
        def held_by(self):
            if not hasattr(self, '_held_by'):
                self._held_by = self.gdb.thread_by_procid(self.held_by_procid)
            return self._held_by

        def __repr__(self):
            return '<PthMutex(addr={:x}, held_by_procid={}>'.format(
                self.addr, self.held_by_procid)

    def __init__(self, gdb, line):
        cols = line.split()
        if len(cols) > 6:
            if cols[0] == '*':
                cols.pop(0)  # active thread
            if cols[1] == 'Thread':
                self.thno = int(cols[0])
                self.thid = hexint(cols[2])
                self.procid = int(cols[4][0:-1])
                self.file = cols.pop()

                if cols[-1] == 'at':
                    cols = cols[5:-1]
                    if cols[1] == 'in':
                        self.funcaddr = hexint(cols[0])
                        cols = cols[2:]
                    else:
                        self.funcaddr = 0
                    self.func = cols.pop(0)
                    self.funcargs = ' '.join(cols)
                    assert self.funcargs.startswith('('), self.funcargs
                    assert self.funcargs.endswith(')'), self.funcargs
                    self.gdb = gdb
                    return
        raise ValueError(line)

    @property
    def backtrace(self):
        if not hasattr(self, '_backtrace'):
            self.gdb.thread(self.thno)
            self._backtrace = self.gdb.backtrace()
        return self._backtrace

    @property
    def waiting_for_mutex(self):
        if not hasattr(self, '_waiting_for_mutex'):
            if self.func == '__lll_lock_wait':
                self._waiting_for_mutex = self._waiting_for_mutex_read()
            else:
                self._waiting_for_mutex = None
        return self._waiting_for_mutex

    def _waiting_for_mutex_read(self):
        self.gdb.thread(self.thno)
        ret = self.gdb.command('frame 2')
        assert '__pthread_mutex_lock' in ret, ret
        ret = self.gdb.command('info args')
        mutex = [i for i in ret.split('\n') if i.startswith('mutex = ')]
        assert len(mutex) == 1, mutex
        mutex_addr = mutex[0].split('=', 1)[1].strip()
        mutex_addr = hexint(mutex_addr.split()[0])
        value = self.gdb.expression('*(pthread_mutex_t*){}'.format(mutex_addr))
        return self.PthMutex(gdb=self.gdb, addr=mutex_addr, value=value)

    def __repr__(self):
        return '<GdbThread(thno={}, thid=0x{:x}, procid={}, func={})>'.format(
            self.thno, self.thid, self.procid, self.func)
