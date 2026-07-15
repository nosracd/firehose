# **Firehose - Environment Setup**

## **Option 1:** Use Docker manually

To build the container, run

```shell
docker pull ubuntu:22.04
docker build --build-arg UID=$(id -u) --build-arg GID=$(id -g) -f docker/Dockerfile -t firehose - < docker/Dockerfile
```

Now you should have an image called `firehose` available for use.

To spin up the container, run:

```shell
docker run --rm -dit -v $(pwd):/firehose -v ~/.ccache:/home/docker/.ccache --name firehose firehose bash
```

Note: podman users may benefit from the addition of the argument `--userns=keep-id` when running the
above command.

Download all Python dependencies using:

```shell
docker exec firehose uv sync
```

Then generate with:

```shell
docker exec firehose ./generate.py --all
```

If the above command was successful, you should be able to see the generated outputs in `output/`.

To spin down the docker container, run:

```shell
docker stop firehose
```

## **Option 2:** Use bare metal (at your own risk)

Install the packages from `docker/Dockerfile` on your operating system, modifying as necessary if
you aren't using the Ubuntu LTS version in the `firehose` image.

Use `uv` to download the necessary Python dependencies, and activate your virtual environment. For
example:

```shell
uv sync
source .venv/bin/activate
```

# **Code Generation [`generate.py`]**

Use the convenience wrapper script `generate.py` in the root directory to easily build, generate,
and stage outputs all at once.

```
python3 generate.py --help

usage: generate.py [-h] [--aspn-icd-dir] [--extra-icd-files-dir] [-b] [-o] [-s] [-a] [--list-targets] [--targets [...]] [--interactive]

Convenience script for generating code from ASPN ICD files and optionally staging the output for use in aspn-generated

options:
  -h, --help                show this help message and exit

  -a, --all                 Generate all output formats

  -o , --output-dir         Directory to place generated output files.
                            Defaults to output
  -s , --staging-input-dir  Staging directory containing any additional non-generated
                            files to push to aspn-generated. Defaults to $PWD/staging

  --aspn-icd-dir            Directory containing input Aspn YAML files for generation.
                            Defaults to $PWD/subprojects/aspn-icd-release-2023
  --extra-icd-files-dir     Directory containing any additional input Aspn YAML files
                            for generation. Defaults to None

  --interactive             Interactive mode to select output formats

  --list-targets            Show a list of all available targets to generate

  --targets [ ...]          List of specific targets to generate.
                            Alternatively use --interactive to select one by one
```

Some examples of how to use the script for various scenarios follow:

## **Interactive mode**

A good place to start familiarizing yourself is to use the interactive mode. If you don't specify
any `--targets` or `--all`, you will be automatically put into `--interactive` mode. This will hold
your hand through all of the parameters and allow you to pick and choose what codegen output you
want.

```shell
python3 generate.py
```

## **Default settings**

```shell
python3 generate.py --all
```

This is equivalent to running:

```shell
python3 generate.py \
    --output-dir ./output \
    --staging-input-dir ./staging \
    --targets \
        aspn_c \
        aspn_dds_idl \
        aspn_dds_cpp \
        aspn_cpp \
        aspn_lcm \
        aspn_py \
        aspn_lcm_translations \
        aspn_ros \
        aspn_ros_translations
```

## **Custom ASPN ICD directory**

```shell
python3 generate.py --aspn-icd-dir /some/path/to/custom/dir --targets aspn_cpp
```

This will look for all `*.yaml` files inside of `/some/path/to/custom/dir` and generate only the c++
output for the files in your custom ASPN ICD directory.

## **Extending/Adding ASPN messages**

If you still want to generate the full normal suite of Aspn messages, but just want to **add** your
own custom extension messages, simply put the YAML files for the extension messages in their own
directory or directories like so:

```shell
python3 generate.py --extra-icd-files-dir /path/to/custom_yamls --targets aspn_cpp aspn_c aspn_py
```

This will look for all `*.yaml` files inside of `dir1` and `dir2` and generate all of the standard
ASPN C/C++ and python code, along with your extension messages.

All output (including all files in `./staging`) will still be placed in the default output directory
`./output`

## **Adding custom ASPN messages to repo that uses aspn-generated**

If you'd like to add your own custom messages you can follow the example below, substituting values
when necessary.

### Optional 1: Manual

You can always make manual changes to a branch of aspn-generated. For example, if you just need an
extension message in ASPN-LCM then you could write that `.lcm` IDL file, add it to the `aspn-lcm`
directory in `aspn-generated`, then run `lcm-gen` to generate a version of ASPN-LCM which contains
the extension message.'

### Option 2: Firehose (At your own risk)

Another route you could take is to run your custom extension message ICD through firehose. The
advantage of this approach is that your extension message will be available for every output. The
disadvantage is firehose is only intended to work on the official core set of ASPN messages. Any
custom messages may deviate from ASPN's unwritten conventions, causing failures in firehose.

If you choose to go this route, there are a couple ways you can get firehose to consume your
extension messages. One way is to use the `--extra-icd-files-dir` argument when calling
`generate.py` to pass the path to a directory containing just your extension messages. Another route
is to push up a new version ASPN-ICD containing your extension messages, then update the version of
ASPN firehose brings in by modifying the ASPN dependency in `pyproject.toml`.

# Building ASPN-ROS

## Explanation

In the main container, the `aspn_ros` subdirectory is created in the output
directory by `generate.py` (see below). It is populated with auto-generated
ROS `.msg` files and staged Python ROS packages. To actually use these,
however, they must be built by `colcon`, ROS's build tool (even though it's
mostly Python, ROS's messaging system requires C extensions). Often, this will
be done by the user (targeting their specific platform). For example,
`smartcables` does this in a ROS Docker container.

## Using CI's ASPN-ROS Ubuntu x86 development packages (easiest)

To ease Python development, however, the CI also automatically builds our ROS
packages for use with Ubuntu 22.04 (ROS Humble) and 24.04 (ROS Jazzy) on x86
machines. Due to the complexity of the ROS build system, the builds occur in
isolated Docker containers. These invoke `colcon build` on the stuff in
`[output-dir]/aspn-ros` and generate installable ROS packages under
`[output-dir]/ros_devel/humble` and `[output-dir]/ros_devel/jazzy`. To use
them (whether inside or outside of a Docker container), simply `source
aspn-generated/ros_devel/humble/setup.bash`, for example (source whichever
one matches your shell; sourcing `setup.sh` from `bash` will fail).

## Building with Docker

If you want ASPN-ROS and aren't using Ubuntu on x86, you'll need to build it
yourself. You can use the same Docker container that the CI uses.

> [!WARNING]
> Before you run a ROS Docker container, make sure you've already run the main
> Docker container (see above), which generated the `[output-dir]/aspn-ros`
> folder. In particular, you'll need to have built targets `aspn_ros` and
> `aspn_ros_translations` (i.e. `python3 generate.py --targets aspn_ros
> aspn_ros_translations` or `python3 generate.py -a`).

To manually build one of these ROS containers, do
```bash
docker build -t firehose-ros:humble --build-arg ROS_DISTRO=humble --build-arg UID=$(id -u) --build-arg GID=$(id -g) -f docker/Dockerfile.ros docker
```
or
```bash
docker build -t firehose-ros:jazzy --build-arg ROS_DISTRO=jazzy --build-arg UID=$(id -u) --build-arg GID=$(id -g) -f docker/Dockerfile.ros docker
```

To run it (which builds the ROS stuff; this can take several minutes), do
```bash
docker run -it -v $(pwd)/output:/output firehose-ros:humble
```
or
```bash
docker run -it -v $(pwd)/output:/output firehose-ros:jazzy
```

Now the `[output-dir]/ros_devel/humble` or `[output-dir]/ros_devel/jazzy`
directory should exist, and its `setup.*` files can be sourced. If you're
trying to *use* ASPN-ROS within a Docker container with ROS (on a non-Ubuntu
system, for example), the directory can be copied into the container before
sourcing.

## Building manually without Docker

> [!WARNING]
> To run `colcon build`, you must either not use a virtual environment, or
> create it with `--system-site-packages` (e.g., `uv venv
> --system-site-packages` or `python3 -m venv .venv --system-site-packages`.
> Otherwise, ROS won't be able to find its Python dependencies installed to the
> system, and you'll get an error.

If you have ROS (including `colcon`) installed locally (see [Humble
Installation Guide](https://docs.ros.org/en/humble/Installation.html) or
[Jazzy Installation Guide](https://docs.ros.org/en/jazzy/Installation.html)),
you can build ASPN-ROS directly. First, make sure the ROS environment is
sourced:

```bash
source /opt/ros/[humble/jazzy]/setup.[sh/bash/zsh]
```

Now, either run the main container (see above) or clone `aspn-generated`.
Then:

```bash
cd [output-dir]/aspn-ros
colcon build
```

This will create an `install/` directory in the current directory with setup
files. To activate the ASPN-ROS environment, `source
install/setup.[sh/bash/zsh]`.
