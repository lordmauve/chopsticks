from setuptools import setup

setup(
    name='chopsticks',
    description='Chopsticks is an orchestration library: it lets you manage ' +
                'and configure remote hosts over SSH.',
    long_description=open('README.rst').read(),
    version=0.2,
    author='Daniel Pope',
    author_email='mauve@mauveweb.co.uk',
    url='https://github.com/lordmauve/chopsticks',
    packages=['chopsticks'],
    zip_safe=False
)
