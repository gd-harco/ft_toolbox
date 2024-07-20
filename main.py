#!/bin/python3.10
import os
import sys

import requests
import argparse
import tarfile
import json
import shutil

parser = argparse.ArgumentParser(description='Jetbrains toolbox cli')

parser.add_argument("action", choices=['list', 'search', 'infos', 'download', 'use', 'config', 'clear', 'remove'])
parser.add_argument("ide", nargs='?', default='all')
parser.add_argument("version", nargs='?', default="latest")
parser.add_argument("cmd", nargs='?')

os.chdir(os.environ.get("HOME", "./"))


def open_config(path):
    file = open(path, "r")
    conf = json.load(file)
    return conf


args = parser.parse_args()

try:
    config_fttb = open_config(".config/fttb/config.json")
except FileNotFoundError:
    if args.action != "config":
        print("run with config firstly")


def get_code(name, config_fttp: dict):
    if name in config_fttp.values():
        return name
    if name in config_fttp['aliases'].keys():
        return config_fttp['aliases'][name]
    return name


def download_file(url, dst):
    with open(dst, "wb") as f:
        response = requests.get(url, stream=True)
        total_length = response.headers.get('content-length')

        if total_length is None:
            f.write(response.content)
        else:
            dl = 0
            total_length = int(total_length)
            for data in response.iter_content(chunk_size=4096):
                dl += len(data)
                f.write(data)
                done = int(100 * dl / total_length)
                print(f"{done}%", end="\r")
                sys.stdout.flush()
            print("")


def list_all(ide):
    if ide == "all":
        codes = ",".join(config_fttb['aliases'].values())
        res = requests.get(
            f"https://data.services.jetbrains.com/products?fields=name,intellijProductCode,description,categories&code={codes}")

        if not res.ok:
            print("request failed")
            sys.exit()

        ides = res.json()

        for ide in ides:
            if ide['intellijProductCode'] is not None and ide['categories'] is not None:
                if "IDE" in ide['categories']:
                    print(f"{ide['name']}\n\n{ide['description']}\n")
    else:
        res = requests.get(
            f"https://data.services.jetbrains.com/products/releases?code={ide}")

        if not res.ok:
            print("request failed")
            sys.exit()

        releases = res.json()[ide][::-1]

        for release in releases:
            if release['notesLink'] is not None:
                print('\x1b]8;;' + release['notesLink'] + '\x1b\\' + release['version'] + '\x1b]8;;\x1b\\')
            else:
                print(release['version'])
            print("")


def search(query):
    res = requests.get(
        "https://data.services.jetbrains.com/products?fields=name,intellijProductCode,description,categories")

    if not res.ok:
        print("request failed")
        sys.exit()

    ides = res.json()

    print(f"search for {query}")

    for ide in ides:
        if ide['intellijProductCode'] is not None and ide['categories'] is not None:
            if "IDE" in ide['categories']:
                if query in ide['name'] or query in ide['intellijProductCode'] or query in ide['description']:
                    print(f"{ide['name']}\ncode: {ide['intellijProductCode']}\n{ide['description']}\n")


def infos(ide):
    ide = get_code(ide, config_fttb)
    res = requests.get(
        f"https://data.services.jetbrains.com/products?fields=name,intellijProductCode,description,categories&code={ide}")

    if not res.ok:
        print("request failed")
        sys.exit()

    if len(res.json()) == 0:
        return
    ide = res.json()[0]

    print(f"{ide['name']}\ncode: {ide['intellijProductCode']}\n{ide['description']}\n")


def get_latest(ide):
    res = requests.get(
        f"https://data.services.jetbrains.com/products?code={ide}&fields=releases")
    if not res.ok:
        print("request failed")
        sys.exit()

    releases = res.json()[0]['releases']
    for release in releases:
        if release["type"] == "release":
            return release['version']
    return releases[0]['version']


def download(ide, version):
    if ide == "all":
        print("invalid IDE code")
        return
    ide = get_code(ide, config_fttb)
    res = requests.get(
        f"https://data.services.jetbrains.com/products?code={ide}&fields=releases")
    if not res.ok:
        print("request failed")
        sys.exit()

    releases = res.json()[0]['releases']
    if version == "latest":
        for release in releases:
            if release["type"] == "release":
                version = release['version']
                break

    if os.path.isdir(f"goinfre/ides/fttb/{ide}-{version}"):
        return version
    for release in releases:
        if release['version'] == version:
            filename = release['downloads']['linux']['link'].split("/")[-1]
            filepath = f".cache/fttb/{filename}"
            download_file(release['downloads']['linux']['link'], filepath)
            file = tarfile.open(filepath)
            file.extractall(path="goinfre/ides/fttb/")
            dst = file.getmembers()[0].name.split('/')[0]
            try:
                shutil.rmtree(f"goinfre/ides/fttb/{ide}-{version}")
            except FileNotFoundError:
                pass
            os.rename(f"goinfre/ides/fttb/{dst}", f"goinfre/ides/fttb/{ide}-{version}")
            return version


def generate_entry(ide, version):
    ide_code = get_code(ide, config_fttb)
    if version == "latest":
        version = get_latest(ide_code)
    res = requests.get(
        f"https://data.services.jetbrains.com/products?code={ide_code}&fields=name,intellijProductCode,description,categories")
    template_file_res = requests.get(
        "https://gist.githubusercontent.com/BenoitRoux0/ece685d71749e9d52a1c03b09a5b6e74/raw/dd5bd0f2a2f24c157a26aa7c97121f883dd6eeef/template.desktop")
    entry = template_file_res.content.decode()
    entry = entry.replace("{name}", res.json()[0]['name'])
    entry = entry.replace("{desc}", res.json()[0]['description'])
    entry = entry.replace("{exec}", f"{os.getcwd()}/goinfre/ides/fttb/{ide_code}-{version}/bin/{ide}.sh %U")
    entry = entry.replace("{icon}", f"{os.getcwd()}/goinfre/ides/fttb/{ide_code}-{version}/bin/{ide}.svg")
    entry_file = open(f".local/share/applications/{ide}.desktop", "w+")
    entry_file.write(entry)
    entry_file.close()
    try:
        os.remove(f"bin/{ide}")
    except FileNotFoundError:
        pass
    os.symlink(f"{os.getcwd()}/goinfre/ides/fttb/{ide_code}-{version}/bin/{ide}.sh", f"bin/{ide}")


def use(ide, version):
    download(ide, version)
    generate_entry(ide, version)


def create_config():
    try:
        os.makedirs(".config/fttb")
    except FileExistsError:
        pass
    try:
        os.makedirs("bin")
    except FileExistsError:
        pass
    try:
        os.makedirs(".cache/fttb")
    except FileExistsError:
        pass
    try:
        os.makedirs("goinfre/ides/fttb")
    except FileExistsError:
        pass
    download_file(
        "https://gist.githubusercontent.com/BenoitRoux0/16b18e10cfd53dcf31a28cb1b38e4303/raw/85e83c6f716fb1ccba39cb88520d0c03f54d9f3e/config.json",
        ".config/fttb/config.json")


def remove(ide, version):
    if ide == "all":
        print("invalid IDE code")
        return
    ide_code = get_code(ide, config_fttb)
    res = requests.get(
        f"https://data.services.jetbrains.com/products?code={ide_code}&fields=releases")
    if not res.ok:
        print("request failed")
        sys.exit()

    releases = res.json()[0]['releases']
    if version == "latest":
        for release in releases:
            if release["type"] == "release":
                version = release['version']
                break

    try:
        shutil.rmtree(f"goinfre/ides/fttb/{ide_code}-{version}")
    except FileNotFoundError:
        pass
    if not os.path.exists(f"bin/{ide}"):
        try:
            os.remove(f"bin/{ide}")
        except FileNotFoundError:
            pass


if args.action == "list":
    list_all(args.ide)
elif args.action == "search":
    search(args.ide)
elif args.action == "infos":
    infos(args.ide)
elif args.action == "download":
    download(args.ide, args.version)
elif args.action == "use":
    use(args.ide, args.version)
    generate_entry(args.ide, args.version)
elif args.action == "config":
    create_config()
elif args.action == "clear":
    try:
        shutil.rmtree(".cache/fttb")
    except FileNotFoundError:
        pass
    os.makedirs(".cache/fttb")
elif args.action == "remove":
    remove(args.ide, args.version)
