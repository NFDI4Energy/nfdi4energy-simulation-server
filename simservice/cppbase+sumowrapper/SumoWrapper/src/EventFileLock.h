#pragma once

#include <cerrno>
#include <fcntl.h>
#include <mutex>
#include <string>
#include <system_error>
#include <sys/stat.h>
#include <unistd.h>

namespace daceDS {

// POSIX record locks match the backend's lockf and Java's FileChannel.lock.
class EventFileLock {
    inline static std::mutex mutex;
    std::unique_lock<std::mutex> threadLock;
    int fd = -1;
public:
    explicit EventFileLock(const std::string& path) : threadLock(mutex) {
        fd = ::open(path.c_str(), O_CREAT | O_WRONLY, 0666);
        if (fd < 0) throw std::system_error(errno, std::generic_category(), "event lock open");
        ::fchmod(fd, 0666);
        struct flock lock{};
        lock.l_type = F_WRLCK;
        lock.l_whence = SEEK_SET;
        while (::fcntl(fd, F_SETLKW, &lock) < 0) {
            if (errno == EINTR) continue;
            int error = errno;
            ::close(fd);
            throw std::system_error(error, std::generic_category(), "event lock acquire");
        }
    }
    ~EventFileLock() { if (fd >= 0) ::close(fd); }
    EventFileLock(const EventFileLock&) = delete;
    EventFileLock& operator=(const EventFileLock&) = delete;
};

} // namespace daceDS
