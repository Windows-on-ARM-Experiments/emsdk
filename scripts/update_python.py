#!/usr/bin/env python3
# Copyright 2020 The Emscripten Authors.  All rights reserved.
# Emscripten is available under two separate licenses, the MIT license and the
# University of Illinois/NCSA Open Source License.  Both these licenses can be
# found in the LICENSE file.

"""Updates the python binaries that we cache store at
http://storage.google.com/webassembly.

We only supply binaries for windows and macOS, but we do it very different ways for those two OSes.

Windows recipe:
  1. Download the "embeddable zip file" version of python from python.org
  2. Remove .pth file to work around https://bugs.python.org/issue34841
  3. Download and install pywin32 in the `site-packages` directory
  4. Re-zip and upload to storage.google.com

macOS recipe:
  1. Clone cpython
  2. Use homebrew to install and configure openssl (for static linking!)
  3. Build cpython from source and use `make install` to create archive.
"""

import glob
import multiprocessing
import os
import platform
import urllib.request
import shutil
import subprocess
import sys
from subprocess import check_call

version = '3.9.10' # 3.9.7 is the first available, but 3.9.10 is the latest in the 3.9 series
major_minor_version = '.'.join(version.split('.')[:2])  # e.g. '3.9.2' -> '3.9'
revision = '4'
download_urls = {
    'amd64':  'https://www.nuget.org/api/v2/package/python/%s' % version,
    'arm64': 'https://www.nuget.org/api/v2/package/pythonarm64/%s' % version
}

pywin32_version = '227'
pywin32_base = 'https://github.com/mhammond/pywin32/releases/download/b%s/' % pywin32_version

upload_base = 'gs://webassembly/emscripten-releases-builds/deps/'


def unzip_cmd():
    # Use 7-Zip if available (https://www.7-zip.org/)
    sevenzip = os.path.join(os.getenv('ProgramFiles', ''), '7-Zip', '7z.exe')
    if os.path.isfile(sevenzip):
        return [sevenzip, 'x']
    # Fall back to 'unzip' tool
    return ['unzip', '-q']


def zip_cmd():
    # Use 7-Zip if available (https://www.7-zip.org/)
    sevenzip = os.path.join(os.getenv('ProgramFiles', ''), '7-Zip', '7z.exe')
    if os.path.isfile(sevenzip):
        return [sevenzip, 'a', '-mx9']
    # Fall back to 'zip' tool
    return ['zip', '-rq']


def make_python_patch(arch):
    # TODO: pywin32 does not support Arm64 yet (https://github.com/mhammond/pywin32/issues/1462)
    pywin32_filename = 'pywin32-%s.win-%s-py%s.exe' % (pywin32_version, 'amd64', major_minor_version)
    filename = 'python-%s-%s.zip' % (version, arch)
    out_filename = 'python-%s-%s-%s+pywin32.zip' % (version, arch, revision)
    if not os.path.exists(pywin32_filename):
        url = pywin32_base + pywin32_filename
        print('Downloading pywin32: ' + url)
        urllib.request.urlretrieve(url, pywin32_filename)

    if not os.path.exists(filename):
        print('Downloading python: ' + download_urls[arch])
        urllib.request.urlretrieve(download_urls[arch], filename)

    os.mkdir('python-nuget')
    check_call(unzip_cmd() + [os.path.abspath(filename)], cwd='python-nuget')

    os.mkdir('pywin32')
    rtn = subprocess.call(unzip_cmd() + [os.path.abspath(pywin32_filename)], cwd='pywin32')
    assert rtn in [0, 1]

    os.mkdir(os.path.join('python-nuget', 'lib'))
    shutil.move(os.path.join('pywin32', 'PLATLIB'), os.path.join('python-nuget', 'toolss', 'Lib', 'site-packages'))

    check_call(zip_cmd() + [os.path.join('..', '..', out_filename), '.'], cwd='python-nuget/tools')

    # cleanup if everything went fine
    shutil.rmtree('python-nuget')
    shutil.rmtree('pywin32')

    print('Created: %s' % out_filename)
    if '--upload' in sys.argv:
      upload_url = upload_base + out_filename
      print('Uploading: ' + upload_url)
      cmd = ['gsutil', 'cp', '-n', out_filename, upload_url]
      print(' '.join(cmd))
      check_call(cmd)


def build_python():
    if sys.platform.startswith('darwin'):
        # Take some rather drastic steps to link openssl and liblzma statically
        # and avoid linking libintl completely.
        osname = 'macos'
        check_call(['brew', 'install', 'openssl', 'xz', 'pkg-config'])
        if platform.machine() == 'x86_64':
            prefix = '/usr/local'
            min_macos_version = '10.11'
        elif platform.machine() == 'arm64':
            prefix = '/opt/homebrew'
            min_macos_version = '11.0'

        # Append '-x86_64' or '-arm64' depending on current arch. (TODO: Do
        # this for Linux too, move this below?)
        osname += '-' + platform.machine()

        for f in [os.path.join(prefix, 'lib', 'libintl.dylib'),
                  os.path.join(prefix, 'include', 'libintl.h'),
                  os.path.join(prefix, 'opt', 'xz', 'lib', 'liblzma.dylib'),
                  os.path.join(prefix, 'opt', 'openssl', 'lib', 'libssl.dylib'),
                  os.path.join(prefix, 'opt', 'openssl', 'lib', 'libcrypto.dylib')]:
            if os.path.exists(f):
                os.remove(f)
        os.environ['PKG_CONFIG_PATH'] = os.path.join(prefix, 'opt', 'openssl', 'lib', 'pkgconfig')
    else:
        osname = 'linux'

    src_dir = 'cpython'
    if not os.path.exists(src_dir):
      check_call(['git', 'clone', 'https://github.com/python/cpython'])
    check_call(['git', 'checkout', 'v' + version], cwd=src_dir)

    env = os.environ
    if sys.platform.startswith('darwin'):
      # Specify the min OS version we want the build to work on
      min_macos_version_line = '-mmacosx-version-min=' + min_macos_version
      build_flags = min_macos_version_line + ' -Werror=partial-availability'
      # Build against latest SDK, but issue an error if using any API that would not work on the min OS version
      env = env.copy()
      env['MACOSX_DEPLOYMENT_TARGET'] = min_macos_version
      configure_args = ['CFLAGS=' + build_flags, 'CXXFLAGS=' + build_flags, 'LDFLAGS=' + min_macos_version_line]
    else:
      configure_args = []
    check_call(['./configure'] + configure_args, cwd=src_dir, env=env)
    check_call(['make', '-j', str(multiprocessing.cpu_count())], cwd=src_dir, env=env)
    check_call(['make', 'install', 'DESTDIR=install'], cwd=src_dir, env=env)

    install_dir = os.path.join(src_dir, 'install')

    # Install requests module.  This is needed in particualr on macOS to ensure
    # SSL certificates are available (certifi in installed and used by requests).
    pybin = os.path.join(src_dir, 'install', 'usr', 'local', 'bin', 'python3')
    pip = os.path.join(src_dir, 'install', 'usr', 'local', 'bin', 'pip3')
    check_call([pybin, '-m', 'ensurepip', '--upgrade'])
    check_call([pybin, pip, 'install', 'requests'])

    dirname = 'python-%s-%s' % (version, revision)
    if os.path.isdir(dirname):
        print('Erasing old build directory ' + dirname)
        shutil.rmtree(dirname)
    os.rename(os.path.join(install_dir, 'usr', 'local'), dirname)
    tarball = 'python-%s-%s-%s.tar.gz' % (version, revision, osname)
    shutil.rmtree(os.path.join(dirname, 'lib', 'python' + major_minor_version, 'test'))
    shutil.rmtree(os.path.join(dirname, 'include'))
    for lib in glob.glob(os.path.join(dirname, 'lib', 'lib*.a')):
        os.remove(lib)
    check_call(['tar', 'zcvf', tarball, dirname])

    print('Created: %s' % tarball)
    if '--upload' in sys.argv:
      print('Uploading: ' + upload_base + tarball)
      check_call(['gsutil', 'cp', '-n', tarball, upload_base + tarball])


def main():
    if sys.platform.startswith('win') or '--win32' in sys.argv:
        if platform.machine() == 'ARM64' or '--arm64' in sys.argv:
            arch = 'arm64'
        else:
            arch = 'amd64'
        make_python_patch(arch)
    else:
        build_python()
    return 0


if __name__ == '__main__':
  sys.exit(main())
