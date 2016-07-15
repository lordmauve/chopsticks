from setuptools import setup

setup(
    name='chopsticks',
    description='Chopsticks is an orchestration library: it lets you manage ' +
                'and configure remote hosts over SSH.',
    long_description=open('README.rst').read(),
    version=0.3,
    author='Daniel Pope',
    author_email='mauve@mauveweb.co.uk',
    url='https://github.com/lordmauve/chopsticks',
    packages=['chopsticks'],
    zip_safe=False,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
        'Operating System :: POSIX',
        'License :: OSI Approved :: Apache Software License',
        'Topic :: System :: Systems Administration'
    ]
)
