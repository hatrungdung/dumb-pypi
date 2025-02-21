from __future__ import annotations

import json
import re

import pytest

from dumb_pypi import main


@pytest.mark.parametrize(
    ('s', 'expected'),
    (
        ('', ('',)),
        ('a0', ('a', 0, '')),
        # digits are always at even indexes so they compare nicely
        ('0a1', ('', 0, 'a', 1, '')),
    ),
)
def test_natural_key(s, expected):
    assert main._natural_key(s) == expected


@pytest.mark.parametrize(('filename', 'name', 'version'), (
    # wheels
    ('dumb_init-1.2.0-py2.py3-none-manylinux1_x86_64.whl', 'dumb_init', '1.2.0'),
    ('ocflib-2016.12.10.1.48-py2.py3-none-any.whl', 'ocflib', '2016.12.10.1.48'),
    ('aspy.yaml-0.2.2-py2.py3-none-any.whl', 'aspy.yaml', '0.2.2'),
    (
        'numpy-1.11.1rc1-cp27-cp27m-macosx_10_6_intel.macosx_10_9_intel.macosx_10_9_x86_64.macosx_10_10_intel.macosx_10_10_x86_64.whl',  # noqa
        'numpy',
        '1.11.1rc1',
    ),
    # Invalid PEP440 version, but still intentionally allowed for compatibility
    # with early releases of dumb-pypi until our next major version.
    ('somepackage-1.2.3.4.post5.post2-py3-none-any.whl', 'somepackage', '1.2.3.4.post5.post2'),

    # other stuff
    ('aspy.yaml.zip', 'aspy.yaml', None),
    ('ocflib-3-4.tar.gz', 'ocflib-3-4', None),
    ('aspy.yaml-0.2.1.tar.gz', 'aspy.yaml', '0.2.1'),
    ('numpy-1.11.0rc1.tar.gz', 'numpy', '1.11.0rc1'),
    ('pandas-0.2beta.tar.gz', 'pandas', '0.2beta'),
    ('scikit-learn-0.15.1.tar.gz', 'scikit-learn', '0.15.1'),
    ('ocflib-2015.11.23.20.2.tar.gz', 'ocflib', '2015.11.23.20.2'),
    ('mesos.cli-0.1.3-py2.7.egg', 'mesos.cli', '0.1.3-py2.7'),

    # inspired by pypiserver's tests
    ('flup-123-1.0.3.dev-20110405.tar.gz', 'flup-123', '1.0.3.dev-20110405'),
    ('package-123-1.3.7+build.11.e0f985a.zip', 'package-123', '1.3.7+build.11.e0f985a'),
))
def test_guess_name_version_from_filename(filename, name, version):
    assert main.guess_name_version_from_filename(filename) == (name, version)


@pytest.mark.parametrize(('filename', 'name', 'version'), (
    ('dumb-init-0.1.0.linux-x86_64.tar.gz', 'dumb-init', '0.1.0'),
    ('greenlet-0.3.4-py3.1-win-amd64.egg', 'greenlet', '0.3.4'),
    ('numpy-1.7.0.win32-py3.1.exe', 'numpy', '1.7.0'),
    ('surf.sesame2-0.2.1_r291-py2.5.egg', 'surf.sesame2', '0.2.1_r291'),
))
def test_guess_name_version_from_filename_only_name(filename, name, version):
    """Broken version check tests.

    The real important thing is to be able to parse the name, but it's nice if
    we can parse the versions too. Unfortunately, we can't yet for these cases.
    """
    parsed_name, parsed_version = main.guess_name_version_from_filename(filename)
    assert parsed_name == name

    # If you can make this assertion fail, great! Move it up above!
    assert parsed_version != version


@pytest.mark.parametrize('filename', (
    '',
    'lol',
    'lol-sup',
    '-20160920.193125.zip',
    'playlyfe-0.1.1-2.7.6-none-any.whl',  # 2.7.6 is not a valid python tag
))
def test_guess_name_version_from_filename_invalid(filename):
    with pytest.raises(ValueError):
        main.guess_name_version_from_filename(filename)


@pytest.mark.parametrize('filename', (
    '',
    'lol',
    'lol-sup',
    '-20160920.193125.zip',
    '..',
    '/blah-2.tar.gz',
    'lol-2.tar.gz/../',
))
def test_package_invalid(filename):
    with pytest.raises(ValueError):
        main.Package.create(filename=filename)


def test_package_url_no_hash():
    package = main.Package.create(filename='f.tar.gz')
    assert package.url('/prefix') == '/prefix/f.tar.gz'


def test_package_url_with_hash():
    package = main.Package.create(filename='f.tar.gz', hash='sha256=badf00d')
    assert package.url('/prefix') == '/prefix/f.tar.gz#sha256=badf00d'


@pytest.mark.parametrize(
    ('filename', 'expected'),
    (
        ("foo-1.0-py2.py3-none-any.whl", "bdist_wheel"),
        ("foo.egg", "bdist_egg"),
        ("foo.zip", "sdist"),
        ("foo.tar.gz", "sdist"),
        ("foo.tar", "sdist"),
    ),
)
def test_package_packagetype(filename, expected):
    package = main.Package.create(filename=filename)
    assert package.packagetype == expected


def test_package_info_all_info():
    package = main.Package.create(
        filename='f-1.0.tar.gz',
        hash='sha256=deadbeef',
        requires_python='>=3.6',
        upload_timestamp=1528586805,
    )
    ret = package.json_info('/prefix')
    assert ret == {
        'digests': {'sha256': 'deadbeef'},
        'filename': 'f-1.0.tar.gz',
        'url': '/prefix/f-1.0.tar.gz',
        'requires_python': '>=3.6',
        'upload_time': '2018-06-09 23:26:45',
        'packagetype': 'sdist',
    }


def test_package_info_wheel_with_local_version():
    ret = main.Package.create(filename='f-1.0+local-py3-none-any.whl')
    assert ret.version == '1.0+local'


def test_package_info_minimal_info():
    ret = main.Package.create(filename='f-1.0.tar.gz').json_info('/prefix')
    assert ret == {
        'filename': 'f-1.0.tar.gz',
        'url': '/prefix/f-1.0.tar.gz',
        'requires_python': None,
        'packagetype': 'sdist',
    }


def test_input_json_all_info():
    package = main.Package.create(
        filename='f-1.0.tar.gz',
        hash='sha256=deadbeef',
        requires_dist=['aspy.yaml'],
        requires_python='>=3.6',
        uploaded_by='asottile',
        upload_timestamp=1528586805,
    )

    assert package.input_json() == {
        'filename': 'f-1.0.tar.gz',
        'hash': 'sha256=deadbeef',
        'requires_dist': ('aspy.yaml',),
        'requires_python': '>=3.6',
        'uploaded_by': 'asottile',
        'upload_timestamp': 1528586805,
    }
    assert main.Package.create(**package.input_json()) == package


def test_input_json_minimal():
    package = main.Package.create(filename='f-1.0.tar.gz')
    assert package.input_json() == {'filename': 'f-1.0.tar.gz'}
    assert main.Package.create(**package.input_json()) == package


def test_package_json_excludes_non_versioned_packages():
    pkgs = [main.Package.create(filename='f.tar.gz')]
    ret = main._package_json(pkgs, '/prefix')
    assert ret == {
        'info': {
            'name': 'f',
            'version': None,
            'requires_dist': None,
            'requires_python': None,
            'platform': 'UNKNOWN',
            'summary': None,
        },
        'releases': {},
        'urls': [],
    }


def test_package_json_packages_with_info():
    pkgs = [
        # These must be sorted oldest first.
        main.Package.create(filename='f-1.0-py2.py3-none-any.whl'),
        main.Package.create(filename='f-1.0.tar.gz'),
        main.Package.create(
            filename='f-2.0-py2.py3-none-any.whl',
            requires_python='>=3.6',
            requires_dist=['dumb-init'],
        ),
        main.Package.create(filename='f-2.0.tar.gz', requires_python='>=3.6'),
    ]
    ret = main._package_json(pkgs, '/prefix')
    assert ret == {
        'info': {
            'name': 'f',
            'version': '2.0',
            'requires_dist': ('dumb-init',),
            'requires_python': '>=3.6',
            'platform': 'UNKNOWN',
            'summary': None,
        },
        'releases': {
            '2.0': [
                {
                    'filename': 'f-2.0-py2.py3-none-any.whl',
                    'url': '/prefix/f-2.0-py2.py3-none-any.whl',
                    'requires_python': '>=3.6',
                    'packagetype': 'bdist_wheel',
                },
                {
                    'filename': 'f-2.0.tar.gz',
                    'url': '/prefix/f-2.0.tar.gz',
                    'requires_python': '>=3.6',
                    'packagetype': 'sdist',
                },
            ],
            '1.0': [
                {
                    'filename': 'f-1.0-py2.py3-none-any.whl',
                    'url': '/prefix/f-1.0-py2.py3-none-any.whl',
                    'requires_python': None,
                    'packagetype': 'bdist_wheel',
                },
                {
                    'filename': 'f-1.0.tar.gz',
                    'url': '/prefix/f-1.0.tar.gz',
                    'requires_python': None,
                    'packagetype': 'sdist',
                },
            ],
        },
        'urls': [
            {
                'filename': 'f-2.0-py2.py3-none-any.whl',
                'url': '/prefix/f-2.0-py2.py3-none-any.whl',
                'requires_python': '>=3.6',
                'packagetype': 'bdist_wheel',
            },
            {
                'filename': 'f-2.0.tar.gz',
                'url': '/prefix/f-2.0.tar.gz',
                'requires_python': '>=3.6',
                'packagetype': 'sdist',
            },
        ],
    }


def test_build_repo_smoke_test(tmpdir):
    package_list = tmpdir.join('package-list')
    package_list.write('ocflib-2016.12.10.1.48-py2.py3-none-any.whl\n')
    main.main((
        '--package-list', package_list.strpath,
        '--output-dir', tmpdir.strpath,
        '--packages-url', '../../pool/',
    ))
    assert tmpdir.join('packages.json').check(file=True)
    assert tmpdir.join('simple').check(dir=True)
    assert tmpdir.join('simple', 'index.html').check(file=True)
    assert tmpdir.join('simple', 'ocflib').check(dir=True)
    assert tmpdir.join('simple', 'ocflib', 'index.html').check(file=True)
    assert tmpdir.join('pypi', 'ocflib', 'json').check(file=True)
    assert tmpdir.join('pypi', 'ocflib', '2016.12.10.1.48', 'json').check(file=True)


def _write_json_package_list(path, packages):
    path.open('w').write('\n'.join(json.dumps(package) for package in packages) + '\n')


def test_build_repo_json_smoke_test(tmpdir):
    package_list = tmpdir.join('package-list')
    _write_json_package_list(
        package_list,
        (
            {
                'filename': 'ocflib-2016.12.10.1.48-py2.py3-none-any.whl',
                'uploaded_by': 'ckuehl',
                'upload_timestamp': 1515783971,
                'hash': 'md5=b1946ac92492d2347c6235b4d2611184',
                'requires_python': '>=3.6',
                'requires_dist': ['dumb-init', 'flask'],
            },
            {
                'filename': 'numpy-1.11.0rc1.tar.gz',
                'upload_timestamp': 1515783971,
            },
            {
                'filename': 'scikit-learn-0.15.1.tar.gz',
            },
            {
                # Version can't be parsed here but it's still allowed.
                'filename': 'aspy.yaml.zip',
            },
        )
    )
    main.main((
        '--package-list-json', package_list.strpath,
        '--output-dir', tmpdir.strpath,
        '--packages-url', '../../pool/',
    ))
    assert tmpdir.join('simple').check(dir=True)
    assert tmpdir.join('simple', 'index.html').check(file=True)
    assert tmpdir.join('simple', 'ocflib').check(dir=True)
    assert tmpdir.join('simple', 'ocflib', 'index.html').check(file=True)
    assert tmpdir.join('pypi', 'ocflib', 'json').check(file=True)
    assert tmpdir.join('pypi', 'ocflib', '2016.12.10.1.48', 'json').check(file=True)


def test_build_repo_partial_rebuild(tmp_path):
    previous_packages = tmp_path / 'previous-packages'
    _write_json_package_list(
        previous_packages,
        (
            {"filename": "a-0.0.1.tar.gz", "upload_timestamp": 1},
            {"filename": "a-0.0.2.tar.gz", "upload_timestamp": 1},

            {"filename": "b-0.0.1.tar.gz", "upload_timestamp": 1},
            {"filename": "b-0.0.2.tar.gz", "upload_timestamp": 2},

            {"filename": "c-0.0.1.tar.gz", "upload_timestamp": 1},
            {"filename": "c-0.0.2.tar.gz", "upload_timestamp": 2},
        ),
    )

    packages = tmp_path / 'packages'
    _write_json_package_list(
        packages,
        (
            # a is unchanged.
            {"filename": "a-0.0.1.tar.gz", "upload_timestamp": 1},
            {"filename": "a-0.0.2.tar.gz", "upload_timestamp": 1},

            # b has a new version.
            {"filename": "b-0.0.1.tar.gz", "upload_timestamp": 1},
            {"filename": "b-0.0.2.tar.gz", "upload_timestamp": 2},
            {"filename": "b-0.0.3.tar.gz", "upload_timestamp": 3},
            # also new, and to test sorting below
            {"filename": "b-0.0.3-py39-none-any.whl", "upload_timestamp": 3},
            {"filename": "b-0.0.3-py310-none-any.whl", "upload_timestamp": 3},

            # timestamp changed on c 0.0.2.
            {"filename": "c-0.0.1.tar.gz", "upload_timestamp": 1},
            {"filename": "c-0.0.2.tar.gz", "upload_timestamp": 999},

            # d is new.
            {"filename": "d-0.0.1.tar.gz", "upload_timestamp": 1},
        ),
    )

    main.main((
        '--previous-package-list-json', str(previous_packages),
        '--package-list-json', str(packages),
        '--output-dir', str(tmp_path),
        '--packages-url', '../../pool/',
    ))

    assert (tmp_path / 'simple' / 'index.html').is_file()

    # a is unchanged.
    assert not (tmp_path / 'simple' / 'a').is_dir()
    assert not (tmp_path / 'pypi' / 'a').is_dir()

    # b has a new version.
    assert (tmp_path / 'simple' / 'b' / 'index.html').is_file()
    assert (tmp_path / 'pypi' / 'b' / 'json').is_file()
    assert (tmp_path / 'pypi' / 'b' / '0.0.3' / 'json').is_file()

    # timestamp changed on c 0.0.2.
    assert (tmp_path / 'simple' / 'c' / 'index.html').is_file()
    assert (tmp_path / 'pypi' / 'c' / 'json').is_file()

    # d is new.
    assert (tmp_path / 'simple' / 'd' / 'index.html').is_file()
    assert (tmp_path / 'pypi' / 'd' / 'json').is_file()
    assert (tmp_path / 'pypi' / 'd' / '0.0.1' / 'json').is_file()

    assert (tmp_path / 'index.html').is_file()
    assert (tmp_path / 'changelog').is_dir()

    expected = [
        # ts@999
        '<a href="../../pool/c-0.0.2.tar.gz"',
        # ts@3
        '<a href="../../pool/b-0.0.3-py39-none-any.whl"',
        '<a href="../../pool/b-0.0.3-py310-none-any.whl"',
        '<a href="../../pool/b-0.0.3.tar.gz"',
        # ts@2
        '<a href="../../pool/b-0.0.2.tar.gz"',
        # ts@1
        '<a href="../../pool/a-0.0.1.tar.gz"',
        '<a href="../../pool/a-0.0.2.tar.gz"',
        '<a href="../../pool/b-0.0.1.tar.gz"',
        '<a href="../../pool/c-0.0.1.tar.gz"',
        '<a href="../../pool/d-0.0.1.tar.gz"',
    ]
    changelog_src = tmp_path.joinpath('changelog/page1.html').read_text()
    found = re.findall('<a href="[^"]+"', changelog_src)
    assert found == expected


def test_build_repo_partial_rebuild_new_version_only(tmp_path):
    package_list = (
        {"filename": "a-0.0.1.tar.gz"},
        {"filename": "b-0.0.1.tar.gz"},
    )
    previous_packages = tmp_path / 'previous-packages'
    packages = tmp_path / 'packages'
    _write_json_package_list(previous_packages, package_list)
    _write_json_package_list(
        packages,
        package_list + ({"filename": "b-0.0.2.tar.gz"},),
    )

    main.main((
        '--previous-package-list-json', str(previous_packages),
        '--package-list-json', str(packages),
        '--output-dir', str(tmp_path),
        '--packages-url', '../../pool/',
    ))

    assert not (tmp_path / 'simple' / 'index.html').is_file()

    assert not (tmp_path / 'simple' / 'a').is_dir()
    assert not (tmp_path / 'pypi' / 'a').is_dir()

    assert (tmp_path / 'simple' / 'b' / 'index.html').is_file()
    assert (tmp_path / 'pypi' / 'b' / 'json').is_file()
    assert (tmp_path / 'pypi' / 'b' / '0.0.1' / 'json').is_file()

    assert (tmp_path / 'index.html').is_file()
    assert (tmp_path / 'changelog').is_dir()


def test_build_repo_partial_rebuild_no_changes_at_all(tmp_path):
    package_list = (
        {"filename": "a-0.0.1.tar.gz"},
        {"filename": "b-0.0.1.tar.gz"},
        {"filename": "c-0.0.1.tar.gz"},
    )
    previous_packages = tmp_path / 'previous-packages'
    packages = tmp_path / 'packages'
    _write_json_package_list(previous_packages, package_list)
    _write_json_package_list(packages, package_list)

    main.main((
        '--previous-package-list-json', str(previous_packages),
        '--package-list-json', str(packages),
        '--output-dir', str(tmp_path),
        '--packages-url', '../../pool/',
    ))

    assert not (tmp_path / 'index.html').is_file()
    assert not (tmp_path / 'simple').is_dir()
    assert not (tmp_path / 'changelog').is_dir()
    assert not (tmp_path / 'pypi').is_dir()


def test_build_repo_no_generate_timestamp(tmpdir):
    package_list = tmpdir.join('package-list')
    package_list.write('pkg-1.0.tar.gz\n')
    main.main((
        '--package-list', package_list.strpath,
        '--output-dir', tmpdir.strpath,
        '--packages-url', '../../pool',
        '--no-generate-timestamp',
    ))
    for p in ('simple/index.html', 'simple/pkg/index.html'):
        assert 'Generated on' not in tmpdir.join(p).read()


def test_build_repo_no_per_release_json(tmp_path):
    package_list = tmp_path / 'package-list'
    package_list.write_text('pkg-1.0.tar.gz\n')
    main.main((
        '--package-list', str(package_list),
        '--output-dir', str(tmp_path),
        '--packages-url', '../../pool',
        '--no-per-release-json',
    ))
    metadata_path = tmp_path / 'pypi' / 'pkg'
    assert set(metadata_path.iterdir()) == {metadata_path / 'json'}


def test_build_repo_even_with_bad_package_names(tmpdir):
    package_list = tmpdir.join('package-list')
    package_list.write('\n'.join((
        '..',
        '/blah-2.tar.gz',
        'lol-2.tar.gz/../',
        'ocflib-2016.12.10.1.48-py2.py3-none-any.whl',
        '',
    )))
    main.main((
        '--package-list', package_list.strpath,
        '--output-dir', tmpdir.strpath,
        '--packages-url', '../../pool/',
    ))
    assert tmpdir.join('simple').check(dir=True)
    assert tmpdir.join('simple', 'index.html').check(file=True)
    assert tmpdir.join('simple', 'ocflib').check(dir=True)
    assert tmpdir.join('simple', 'ocflib', 'index.html').check(file=True)


def test_atomic_write(tmpdir):
    a = tmpdir.join('a')
    a.write('sup')
    with main.atomic_write(a.strpath) as f:
        f.write('lol')
    assert a.read() == 'lol'


def test_atomic_write_exception(tmpdir):
    a = tmpdir.join('a')
    a.write('sup')
    with pytest.raises(ValueError):
        with main.atomic_write(a.strpath) as f:
            f.write('lol')
            f.flush()
            raise ValueError('sorry buddy')
    assert a.read() == 'sup'


def test_sorting():
    test_packages = [
        main.Package.create(filename=name)
        for name in (
            'fluffy-server-1.2.0.tar.gz',
            'fluffy_server-1.1.0-py2.py3-none-any.whl',
            'wsgi-mod-rpaf-2.0.0.tar.gz',
            'fluffy-server-10.0.0.tar.gz',
            'aspy.yaml-0.2.1.tar.gz',
            'wsgi-mod-rpaf-1.0.1.tar.gz',
            'aspy.yaml-0.2.1-py3-none-any.whl',
            'fluffy-server-1.0.0.tar.gz',
            'aspy.yaml-0.2.0-py2-none-any.whl',
            'fluffy_server-10.0.0-py2.py3-none-any.whl',
            'aspy.yaml-0.2.1-py2-none-any.whl',
            'fluffy-server-1.1.0.tar.gz',
            'fluffy_server-1.0.0-py2.py3-none-any.whl',
            'fluffy_server-1.2.0-py2.py3-none-any.whl',
            'zpkg-1-cp38-cp38-manylinux_2_28_aarch64.whl',
            'zpkg-1-cp39-cp39-manylinux_2_28_aarch64.whl',
            'zpkg-1-cp310-cp310-manylinux_2_28_aarch64.whl',
        )
    ]
    sorted_names = [package.filename for package in sorted(test_packages)]
    assert sorted_names == [
        'aspy.yaml-0.2.0-py2-none-any.whl',
        'aspy.yaml-0.2.1-py2-none-any.whl',
        'aspy.yaml-0.2.1-py3-none-any.whl',
        'aspy.yaml-0.2.1.tar.gz',
        'fluffy_server-1.0.0-py2.py3-none-any.whl',
        'fluffy-server-1.0.0.tar.gz',
        'fluffy_server-1.1.0-py2.py3-none-any.whl',
        'fluffy-server-1.1.0.tar.gz',
        'fluffy_server-1.2.0-py2.py3-none-any.whl',
        'fluffy-server-1.2.0.tar.gz',
        'fluffy_server-10.0.0-py2.py3-none-any.whl',
        'fluffy-server-10.0.0.tar.gz',
        'wsgi-mod-rpaf-1.0.1.tar.gz',
        'wsgi-mod-rpaf-2.0.0.tar.gz',
        'zpkg-1-cp38-cp38-manylinux_2_28_aarch64.whl',
        'zpkg-1-cp39-cp39-manylinux_2_28_aarch64.whl',
        'zpkg-1-cp310-cp310-manylinux_2_28_aarch64.whl',
    ]
