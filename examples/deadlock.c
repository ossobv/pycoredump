/* deadlock.c, thread deadlock example -- Walter Doekes, OSSO B.V. 2015 */
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

volatile int done = 0;
pthread_mutex_t globallock = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t speciallock = PTHREAD_MUTEX_INITIALIZER;

void *irrelevant(void *ptr)
{
	sleep(2);
	pthread_mutex_lock(&globallock);
	pthread_mutex_unlock(&globallock);
	return NULL;
}

void *normal(void *ptr)
{
	pthread_mutex_lock(&globallock);
	sleep(1);
	pthread_mutex_lock(&speciallock);
	sleep(1);
	done += 1;
	pthread_mutex_unlock(&speciallock);
	pthread_mutex_unlock(&globallock);
	return NULL;
}

void *inverted(void *ptr)
{
	pthread_mutex_lock(&speciallock);
	sleep(1);
	pthread_mutex_lock(&globallock);
	sleep(1);
	done += 1;
	pthread_mutex_unlock(&globallock);
	pthread_mutex_unlock(&speciallock);
	return NULL;
}

void *other(void *ptr)
{
	while (done < 2)
		sleep(1);
	return NULL;
}

void alarmfire(int signum)
{
	abort();
}

int main(int argc, const char *const *argv)
{
	typedef void *(*start_routine) (void *);
	pthread_t threads[8] = {0, 0, 0, 0, 0, 0, 0, 0};
	start_routine funcs[8] = {normal, irrelevant, other, irrelevant,
				  inverted, other, other, irrelevant};
	const int n = 8;
	int i;

	if (argc > 1 && strcmp(argv[1], "nolock") == 0)
		funcs[4] = normal; /* no locking inversion */

	signal(SIGALRM, alarmfire);
	alarm(8);

	for (i = 0; i < n; ++i) {
		printf("Starting %d...\n", i);
		if (pthread_create(&threads[i], NULL, funcs[i], NULL))
			exit(1);
	}
	printf("Up and running!\n");
	for (i = 0; i < n; ++i) {
		printf("Joining %d...\n", i);
		if (pthread_join(threads[i], NULL))
			exit(1);
	}
	printf("Joined, all is good!\n");
	alarm(0);
	return 0;
}
