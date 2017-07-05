Examples
========

In this example, we install a configuration file to three servers in parallel
and then restart a service::

    import subprocess
    from chopsticks.group import Group

    webservers = Group(['www1', 'www2', 'www3'])

    webservers.put('uwsgi.ini', '/srv/www/supervisor/uwsgi.ini')
    webservers.call(
        subprocess.check_output,
        'supervisord restart uwsgi',
        shell=True
    ).raise_failures()
    webservers.close()

