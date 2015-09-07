# debug-deadlock -- pycoredump -- Walter Doekes, OSSO B.V. 2015
from __future__ import absolute_import, print_function
from collections import defaultdict
from pycoredump import GdbWithThreads
import sys

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
        relevant_threads.add(th.waiting_for_mutex.held_by)

    print('-- relevant threads --')
    for th in relevant_threads:
        print(th)
        print(th.backtrace)
        print('    waits for', th.waiting_for_mutex.held_by)
        print()
