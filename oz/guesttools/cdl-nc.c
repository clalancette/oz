#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>

void usage(void)
{
  fprintf(stderr, "Usage: static-nc [OPTIONS] <host> <port>\n");
  fprintf(stderr, "\nOPTIONS:\n");
  fprintf(stderr, " -h\tPrint this help message\n");
  exit(1);
}

int main(int argc, char *argv[])
{
  int s, c, ret, port, retval = 0;
  struct sockaddr_in a;
  const char *host;
  ssize_t bytes;

  while ((c = getopt(argc, argv, ":h")) != -1) {
    switch(c) {
    case 'h':
      usage();
      break;
    default:
      usage();
      break;
    }
  }

  if ((argc - optind) != 2)
    usage();

  host = argv[optind++];
  port = atoi(argv[optind++]);

  s = socket(AF_INET, SOCK_STREAM, 0);
  if (s < 0) {
    fprintf(stderr, "Error creating socket: %s\n", strerror(errno));
    return 1;
  }

  memset(&a, 0, sizeof(struct sockaddr_in));
  a.sin_port = htons(port);
  a.sin_family = AF_INET;

  if (inet_aton(host, &a.sin_addr) == 0) {
    fprintf(stderr, "Invalid address %s\n", host);
    retval = 3;
    goto cleanup;
  }

  ret = connect(s, (struct sockaddr *)&a, sizeof(struct sockaddr_in));
  if (ret < 0) {
    fprintf(stderr, "Failed to connect to %s:%d\n", host, port);
    retval = 2;
    goto cleanup;
  }

  bytes = write(s, "hello", 5);
  if (bytes != 5) {
    fprintf(stderr, "Expected to write 5 bytes to socket, wrote %zd\n", bytes);
    retval = 3;
    goto cleanup;
  }

 cleanup:
  close(s);

  return retval;
}
