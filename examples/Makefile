CFLAGS = -Wall -g -O0
LDFLAGS = -Wall -g -O0 -pthread

deadlock.core: deadlock
	./deadlock nolock  # test
	gdb ./deadlock -batch \
	  -ex run \
	  -ex 'info threads' \
	  -ex 'generate-core-file deadlock.core' \
	  -ex detach \
	  -ex quit

deadlock: deadlock.o
