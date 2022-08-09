"""
This script is for defining macros for MkDocs macros plugin.

The hook function is `define_env`.
"""

import math
import csv
from functools import partial
from pathlib import Path

from tabulate import tabulate


def define_env(env):
    """Hook function"""

    env.macro(pi_string)
    env.macro(partial(csv_table, env=env), "csv_table")
    env.macro(youtube)


def pi_string(dp=2):
    fmt = "{:." + str(dp) + "f}"
    return fmt.format(math.pi)


def csv_table(
    file_path,
    headers="firstrow",
    tablefmt="pipe",
    floatfmt="g",
    numalign="default",
    stralign="default",
    missingval="",
    showindex="default",
    disable_numparse=False,
    colalign=None,
    env=None,
):
    if env is None:
        raise Exception("csv_table env does not exist!")

    csvfile_path = Path(env.conf["docs_dir"]).joinpath(file_path)

    with csvfile_path.open(newline="") as csvfile:
        csvreader = csv.reader(csvfile)
        table = list(csvreader)

    md_table = tabulate(
        table,
        headers=headers,
        tablefmt=tablefmt,
        floatfmt=floatfmt,
        numalign=numalign,
        stralign=stralign,
        missingval=missingval,
        showindex=showindex,
        disable_numparse=disable_numparse,
        colalign=colalign,
    )

    return md_table


def youtube(src, width=640, height=360, frameborder=0):
    url_base = "https://www.youtube.com/embed/"

    if not src.startswith(url_base):
        if src.startswith("https://www.youtube.com/watch?v="):
            src = url_base + src.split("watch?v=")[-1]
        elif src.startswith("https://youtu.be/"):
            src = url_base + src.split("https://youtu.be/")[-1]
        else:
            src = url_base + src.split("/")[-1]

    iframe_tmpl = '<iframe \
        width="{}" \
        height="{}" \
        src="{}" \
        frameborder="{}" \
        allow="accelerometer; \
            autoplay; \
            clipboard-write; \
            encrypted-media; \
            gyroscope; \
            picture-in-picture" \
        allowfullscreen\
        ></iframe>'

    return iframe_tmpl.format(width, height, src, frameborder)
