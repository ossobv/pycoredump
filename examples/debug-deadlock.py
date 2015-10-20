# debug-deadlock -- pycoredump -- Walter Doekes, OSSO B.V. 2015
from __future__ import absolute_import, print_function
from collections import defaultdict
from pycoredump import GdbWithThreads
import sys

# $ sudo env PYTHONPATH=`pwd` python examples/debug-deadlock.py \
#     `sudo which asterisk` \
#     /var/spool/asterisk/core.vgua0-tc2-2015-10-20T10:30:11+0200
program, corefile = sys.argv[1:]

with GdbWithThreads(program=program, corefile=corefile) as dump:
    print('-- all waiting threads --')
    waiting_for = defaultdict(list)
    for th in dump.threads:
        if th.waiting_for_mutex:
            print(th)
            print('    waits for', th.waiting_for_mutex.held_by)
            waiting_for[th.waiting_for_mutex.held_by].append(
                th)
    print()

    threads_waited_on_the_least = [
       (k, len(v)) for k, v in waiting_for.items()]
    threads_waited_on_the_least.sort(key=(lambda x: x[1]))
    num = threads_waited_on_the_least[0][1]
    threads_waited_on_the_least = [
       k for k, v in threads_waited_on_the_least if v <= num]
    relevant_threads = set()
    for th in threads_waited_on_the_least:
        relevant_threads.add(th)
	if th.waiting_for_mutex:
            relevant_threads.add(th.waiting_for_mutex.held_by)

    print('-- relevant threads --')
    for th in relevant_threads:
        print(th)
        print(th.backtrace)
	if th.waiting_for_mutex:
            print('    waits for', th.waiting_for_mutex.held_by)
        print()

    # If we're waiting for a dead thread, the above would have shown us way too
    # little.
    for th in relevant_threads:
	if th.thno == -1:
	    for waiting in waiting_for[th]:
	        print('-- waiting on dead thread {} --'.format(th))
		print(waiting)
		print(waiting.backtrace)
                print()
