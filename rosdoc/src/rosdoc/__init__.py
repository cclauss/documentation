#!/usr/bin/env python
# Software License Agreement (BSD License)
#
# Copyright (c) 2008, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Revision $Id$

import sys
import os
import time
import traceback
from subprocess import Popen, PIPE

NAME='rosdoc'

from . rdcore import *
from . import upload

from . import msgenator
from . import docindex 
from . import licenseindex
from . import epyenator
from . import sphinxenator
from . import landing_page

def get_optparse(name):
    """
    Retrieve default option parser for rosdoc. Useful if building an
    extended rosdoc tool with additional options.
    """
    from optparse import OptionParser
    parser = OptionParser(usage="usage: %prog [options] [packages...]", prog=name)
    parser.add_option("-n", "--name",metavar="NAME",
                      dest="name", default="ROS Package", 
                      help="Name for documentation set")
    parser.add_option("-q", "--quiet",action="store_true", default=False,
                      dest="quiet",
                      help="Suppress doxygen errors")
    parser.add_option("--paths",metavar="PATHS",
                      dest="paths", default=None, 
                      help="package paths to document")
    parser.add_option("--no-rxdeps", action="store_true",
                      dest="no_rxdeps", default=False, 
                      help="disable rxdeps")
    parser.add_option("-o",metavar="OUTPUT_DIRECTORY",
                      dest="docdir", default='doc', 
                      help="directory to write documentation to")
    parser.add_option("--upload",action="store", default=None,
                      dest="upload", metavar="RSYNC_TARGET",
                      help="rsync target argument")
    return parser
    
def generate_docs(ctx, quiet=True, no_rxdeps=True):
    timings = ctx.timings
    artifacts = []
    
    # Collect all packages that mention rosmake as a builder, and build them first
    start = time.time()
    to_rosmake = []
    for package in ctx.rd_configs:
            if (package in ctx.doc_packages and
                ctx.should_document(package) and
                ctx.has_builder(package, 'rosmake')):
                to_rosmake.append(package)

    if to_rosmake and ctx.allow_rosmake:
        # command = ['rosmake', '--status-rate=0'] + to_rosmake
        command = ['rosmake', '-V'] + to_rosmake
        print " ".join(command)
        started = time.time()
        try:
            (stdoutdata, _) = Popen(command, stdout=PIPE).communicate()
            print stdoutdata
        except:
            print "command failed"
        print "rosmake took %ds" % (time.time() - started)
        timings['rosmake'] = time.time() - start

    # Generate Doxygen
    #  - this can become a plugin once we move rxdeps out of it
    start = time.time()
    import doxygenator
    try:
        artifacts.extend(doxygenator.generate_doxygen(ctx, disable_rxdeps=no_rxdeps))
    except Exception, e:
        traceback.print_exc()
        print >> sys.stderr, "doxygenator completely failed"
        doxy_success = []                
    timings['doxygen'] = time.time() - start

    plugins = [
        ('epydoc', epyenator.generate_epydoc),
        ('sphinx', sphinxenator.generate_sphinx),
        ('msg', msgenator.generate_msg_docs),
        ('landing-page', landing_page.generate_landing_page),
        ('doc-index', docindex.generate_doc_index),
        ('license-index', licenseindex.generate_license_index),
               ]

    for plugin_name, plugin in plugins:
        start = time.time()
        try:
            artifacts.extend(plugin(ctx))
        except Exception, e:
            traceback.print_exc()
            print >> sys.stderr, "plugin [%s] failed"%(plugin_name)
        timings[plugin_name] = time.time() - start
            
    # support files
    # TODO: convert to plugin
    start = time.time()
    import shutil
    for f in ['styles.css', 'msg-styles.css']:
        styles_in = os.path.join(ctx.template_dir, f)
        styles_css = os.path.join(ctx.docdir, f)
        print "copying",styles_in, "to", styles_css
        shutil.copyfile(styles_in, styles_css)
        artifacts.append(styles_css)
    timings['support_files'] = time.time() - start

    return list(set(artifacts))


def main():
    parser = get_optparse(NAME)
    options, package_filters = parser.parse_args()

    # Load the ROS environment
    ctx = RosdocContext(options.name, options.docdir,
                        package_filters=package_filters, path_filters=options.paths)
    ctx.quiet = options.quiet
    try:
        ctx.init()

        artifacts = generate_docs(ctx)

        start = time.time()
        if options.upload:
            upload.upload(ctx, artifacts, options.upload)
        ctx.timings['upload'] = time.time() - start

        print "Timings"
        for k, v in ctx.timings.iteritems():
            print " * %.2f %s"%(v, k)

    except:
        traceback.print_exc()
        sys.exit(1)
