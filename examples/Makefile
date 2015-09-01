CFLAGS = -Wall -g -O0
LDFLAGS = -Wall -g -O0 -pthread

.PHONY: debug-deadlock
debug-deadlock: deadlock.core
	PYTHONPATH=`pwd`/../ python debug-deadlock.py \
	  ./deadlock ./deadlock.core

.PHONY: clean
clean:
	$(RM) deadlock deadlock.o deadlock.core

deadlock.core: deadlock
	./deadlock nolock  # test
	gdb ./deadlock -batch \
	  -ex run \
	  -ex 'info threads' \
	  -ex 'generate-core-file deadlock.core' \
	  -ex detach \
	  -ex quit

deadlock: deadlock.o
