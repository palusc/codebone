// Main executable of codebone.app. macOS attaches menu-bar items to the bundle's own
// main executable, so Python must run inside this process (not via exec of another binary).
// libpython is the bundled, relocatable one (@rpath), so nothing here depends on the build machine.
#include <Python.h>
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    char exe[PATH_MAX], real[PATH_MAX], home[PATH_MAX], script[PATH_MAX];
    uint32_t n = sizeof exe;
    if (_NSGetExecutablePath(exe, &n) != 0 || !realpath(exe, real)) return 1;
    char *macos = dirname(real);  // .../Contents/MacOS
    snprintf(home, sizeof home, "%s/../Resources/venv", macos);
    snprintf(script, sizeof script, "%s/../Resources/src/codebone_main.py", macos);
    setenv("PYTHONHOME", home, 1);
    char *args[] = {real, script, NULL};
    return Py_BytesMain(2, args);
}
