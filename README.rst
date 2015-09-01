Python wrapper around GDB to examine core dumps
===============================================

Deadlocks in C programs are a pain to debug. But if you know your way
around GDB, you may get more out a core dump than you think.


Deadlock example
----------------

For the following example, we'll create a core dump of a program that
intentionally deadlocks: ``examples/deadlock``

That example application spawns *eight* threads of which *five* threads
use locks and *two of those* lock each other -- because of a locking
inversion.

The application has an alarm set, so it will generate ``SIGABRT`` core
file after a few seconds. That's nice because now we have something to
debug.

Go into the ``examples/`` dir and type ``make``. It wil self-test the
deadlock application and then create the file ``deadlock.core`` using
``gdb``.

.. code-block:: console

    $ cd examples/
    $ make
    cc -Wall -g -O0   -c -o deadlock.o deadlock.c
    cc -Wall -g -O0 -pthread  deadlock.o   -o deadlock
    ./deadlock nolock
    ...

If all went well, you now a ``deadlock.core`` file:

.. code-block:: console

    $ ls -l deadlock.core
    -rw-rw-r-- 1 walter walter 17448904 sep  1 21:04 deadlock.core


Manual GDB debugging
--------------------

If you open the core file with GDB, you should manually be able to find
out which threads lock each other; but it's tedious work.

For example:

.. code-block:: console

    $ gdb ./deadlock deadlock.core
    (gdb) info threads
      Id   Target Id         Frame
      9    Thread 0x2aaaaaaef040 (LWP 27444) 0x00002aaaaaf24cc9 in __GI_raise
        (sig=sig@entry=6) at ../nptl/sysdeps/unix/sysv/linux/raise.c:56
      8    Thread 0x2aaaab4b3700 (LWP 27448) __lll_lock_wait ()
        at ../nptl/sysdeps/unix/sysv/linux/x86_64/lowlevellock.S:135
      7    Thread 0x2aaaab6b4700 (LWP 27449) __lll_lock_wait ()
        at ../nptl/sysdeps/unix/sysv/linux/x86_64/lowlevellock.S:135
      6    Thread 0x2aaaab8b5700 (LWP 27450) 0x00002aaaaafaef3d in nanosleep
        () at ../sysdeps/unix/syscall-template.S:81
      5    Thread 0x2aaaabab6700 (LWP 27451) __lll_lock_wait ()
        at ../nptl/sysdeps/unix/sysv/linux/x86_64/lowlevellock.S:135
      4    Thread 0x2aaaabcb7700 (LWP 27452) __lll_lock_wait ()
        at ../nptl/sysdeps/unix/sysv/linux/x86_64/lowlevellock.S:135
      3    Thread 0x2aaaabeb8700 (LWP 27453) 0x00002aaaaafaef3d in nanosleep
        () at ../sysdeps/unix/syscall-template.S:81
      2    Thread 0x2aaaac0b9700 (LWP 27454) 0x00002aaaaafaef3d in nanosleep
        () at ../sysdeps/unix/syscall-template.S:81
    * 1    Thread 0x2aaaac2ba700 (LWP 27455) __lll_lock_wait ()
        at ../nptl/sysdeps/unix/sysv/linux/x86_64/lowlevellock.S:135

Okay, 9 threads. And now?

#. Check only the threads that are waiting for a lock: those in
   ``__lll_lock_wait``.
#. For those threads, check which locks they're waiting for, and who is
   holding those locks.

Somewhat like this:

.. code-block:: console

    (gdb) thread 8
    [Switching to thread 8 (Thread 0x2aaaab4b3700 (LWP 27448))]
    #0  __lll_lock_wait ()
        at ../nptl/sysdeps/unix/sysv/linux/x86_64/lowlevellock.S:135
        135 in ../nptl/sysdeps/unix/sysv/linux/x86_64/lowlevellock.S
    (gdb) frame 2
    #2  0x00002aaaaacda480 in __GI___pthread_mutex_lock (
          mutex=0x602120 <speciallock>)
        at ../nptl/pthread_mutex_lock.c:79
        79 ../nptl/pthread_mutex_lock.c: No such file or directory.
    (gdb) print *(pthread_mutex_t*)mutex
    $1 = {__data = {__lock = 2, __count = 0, __owner = 27452,
          __nusers = 1, __kind = 0, __spins = 0, __elision = 0,
          __list = {__prev = 0x0, __next = 0x0}},
          __size = "\002...", '\000' <repeats 26 times>, __align = 2}

There, the ``__owner`` shows that the mutex that thread 8 is waiting is
waiting for, is (light weight) process id (LWP) 27452, which corresponds
to thread 4.

Repeat this step for all threads that are waiting for a lock.

Tedious, huh?


Automated using pycoredump
--------------------------

Go back into the root of this project, and fire up the example code
in ``pycoredump``. Like this:

.. code-block:: console

    $ python pycoredump/__init__.py ./examples/deadlock ./examples/deadlock.core
    -- all waiting threads --
    <GdbThread(thno=8, thid=0x2aaaab4b3700, procid=27448, func=__lll_lock_wait)>
        waits for <GdbThread(thno=4, thid=0x2aaaabcb7700, procid=27452, func=__lll_lock_wait)>
    <GdbThread(thno=7, thid=0x2aaaab6b4700, procid=27449, func=__lll_lock_wait)>
        waits for <GdbThread(thno=8, thid=0x2aaaab4b3700, procid=27448, func=__lll_lock_wait)>
    <GdbThread(thno=5, thid=0x2aaaabab6700, procid=27451, func=__lll_lock_wait)>
        waits for <GdbThread(thno=8, thid=0x2aaaab4b3700, procid=27448, func=__lll_lock_wait)>
    <GdbThread(thno=4, thid=0x2aaaabcb7700, procid=27452, func=__lll_lock_wait)>
        waits for <GdbThread(thno=8, thid=0x2aaaab4b3700, procid=27448, func=__lll_lock_wait)>
    <GdbThread(thno=1, thid=0x2aaaac2ba700, procid=27455, func=__lll_lock_wait)>
        waits for <GdbThread(thno=8, thid=0x2aaaab4b3700, procid=27448, func=__lll_lock_wait)>

Nice, only the threads that are waiting for a lock. And what they're
waiting for.

And it gets better, filtered by relevant threads only: the ``normal``
and ``inverted`` threads. With a bit of backtrace appended.

.. code-block:: console

    -- relevant threads --
    <GdbThread(thno=8, thid=0x2aaaab4b3700, procid=27448, func=__lll_lock_wait)>
    <GdbBacktrace(
     <GdbFrame(no=0, func=__lll_lock_wait, file=../nptl/sysdeps/unix/sysv/linux/x86_64/lowlevellock.S:135>
     <GdbFrame(no=1, func=_L_lock_909, file=/lib/x86_64-linux-gnu/libpthread.so.0>
     <GdbFrame(no=2, func=__GI___pthread_mutex_lock, file=../nptl/pthread_mutex_lock.c:79>
     <GdbFrame(no=3, func=normal, file=deadlock.c:24>
     <GdbFrame(no=4, func=start_thread, file=pthread_create.c:312>
     <GdbFrame(no=5, func=clone, file=../sysdeps/unix/sysv/linux/x86_64/clone.S:111>
    )>
        waits for <GdbThread(thno=4, thid=0x2aaaabcb7700, procid=27452, func=__lll_lock_wait)>

    <GdbThread(thno=4, thid=0x2aaaabcb7700, procid=27452, func=__lll_lock_wait)>
    <GdbBacktrace(
     <GdbFrame(no=0, func=__lll_lock_wait, file=../nptl/sysdeps/unix/sysv/linux/x86_64/lowlevellock.S:135>
     <GdbFrame(no=1, func=_L_lock_909, file=/lib/x86_64-linux-gnu/libpthread.so.0>
     <GdbFrame(no=2, func=__GI___pthread_mutex_lock, file=../nptl/pthread_mutex_lock.c:79>
     <GdbFrame(no=3, func=inverted, file=deadlock.c:36>
     <GdbFrame(no=4, func=start_thread, file=pthread_create.c:312>
     <GdbFrame(no=5, func=clone, file=../sysdeps/unix/sysv/linux/x86_64/clone.S:111>
    )>
        waits for <GdbThread(thno=8, thid=0x2aaaab4b3700, procid=27448, func=__lll_lock_wait)>

Better, yes?

That's generated by just 25 lines of code that calls the ``pycoredump``
library.


Conclusion
----------

Obviously the ``pycoredump`` library could use a lot of extra features,
and cleanup, but this simple example demonstrates how it can make your
deadlock debugging life easier.

I've used the manual technique to find the cause of a deadlock in the
Asterisk PBX software. That software supports a thread-debugging mode,
but that's so slow that it's unusable in production systems. Luckily,
much of the needed info is there; you just have to find it.

And now, finding it may have become a little bit simpler.
