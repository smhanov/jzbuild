#!/usr/bin/python
"""
JZBUILD Javascript build system

By Steve Hanov (steve.hanov@gmail.com)

This is free software. It is released to the public domain. 

------------------------------------------------------------------------------
------------------------------------------------------------------------------
------------------------------------------------------------------------------
The JZBUILD software may include jslint software, which is covered under the
following license.

/*
Copyright (c) 2002 Douglas Crockford  (www.JSLint.com)

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

The Software shall be used for Good, not Evil.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/

------------------------------------------------------------------------------
------------------------------------------------------------------------------
------------------------------------------------------------------------------
Coffeescript is covered under the following license.

Copyright (c) 2011 Jeremy Ashkenas

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.
------------------------------------------------------------------------------
------------------------------------------------------------------------------
------------------------------------------------------------------------------
JCoffeeScript is covered under the following license:
/*
 * Copyright 2010 David Yeung
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
"""

import re
import os
import platform
import subprocess
import sys
import urllib2
import cStringIO
import zipfile
import glob
import base64
import zlib
import tempfile
import atexit

MAKEFILE_NAME = "makefile.jz"

NEVER_CHECK_THESE_FILES = """
jquery.min.js
jquery.js
prototype.js
""".split("\n")

COMPILERS = {
    # Name of the compiler, as specified in the makefile and the --compiler
    # option.
    "closure": {
        # URL at which to download a zipfile of the compiler
        "download":
            "http://closure-compiler.googlecode.com/files/compiler-latest.zip",

        # full path in the zip file of the compiler.
        "filename":
            "compiler.jar",

        # These options are always specified.
        "requiredOptions": [],    

        # Command line option that must precede each input filename
        "inputOption":
            "--js",

        # Command line option to specify the output file
        "outputOption":
            "--js_output_file",

        # Default options to use if none are specified
        "defaultOptions": [
            "--compilation_level", "SIMPLE_OPTIMIZATIONS",
            "--warning_level", "VERBOSE" ],

        # Options to use if none are specified and user is doing a --release
        # build.
        "releaseOptions": [
            "--compilation_level", "ADVANCED_OPTIMIZATIONS",
            "--warning_level", "VERBOSE" ],

        # Set this to True if the tool can't take the input on the command
        # line, and instead requires input to be concatenated together and
        # piped to its standard input.
        "requiresStdin": False,

    },

    "yui": {
        "download":
            "http://yui.zenfs.com/releases/yuicompressor/yuicompressor-2.4.2.zip",
        "filename":
            "yuicompressor-2.4.2/build/yuicompressor-2.4.2.jar",
        "requiredOptions": ["--type", "js"],
        "inputOption": "",
        "outputOption": "-o",
        "defaultOptions": [],    
        "requiresStdin": True,
    },
}

EXTERNS = {
    "jquery-1.5.js":
        "http://closure-compiler.googlecode.com/svn/trunk/contrib/externs/jquery-1.5.js",
    "json.js":
        "http://closure-compiler.googlecode.com/svn/trunk/contrib/externs/json.js",
    "jquery-mobile.js":
        "http://github.com/smhanov/jzbuild/raw/master/externs/jquery-mobile.js",
}

JCOFFEESCRIPT_URL = \
    "http://github.com/downloads/smhanov/jcoffeescript/jcoffeescript-1.1.jar"
COFFEESCRIPT_URL = \
    "http://github.com/downloads/smhanov/coffee-script/coffee-script.js"
def GetStorageFolder():
    """Returns the path to a location where we can store downloads"""

    # Seems to work on windows 7 too   
    path = os.path.join(os.path.expanduser("~"), ".jzbuild")
    if not os.path.isdir(path):
        print "Creating %s" % path
        os.mkdir(path)
    return path 

JCOFFEESCRIPT_PATH = \
    os.path.join(GetStorageFolder(), os.path.basename( JCOFFEESCRIPT_URL ) )

COFFEESCRIPT_PATH = \
    os.path.join(GetStorageFolder(), os.path.basename( COFFEESCRIPT_URL ) )

VALID_COMPILERS = COMPILERS.keys();
VALID_COMPILERS.append("cat")

MAN_PAGE = """
NAME
    
    jzbuild - The easy Javascript build system

SYNOPSIS
    
    jzbuild [files or projects]

DESCRIPTION

    Runs jslint and joins together javascript input files, optionally using the
    Google closure compiler or YUI compressor to reduce file size and find more
    errors.

    Jzbuild looks for a file named "makefile.jz" in the current folder. If
    found, it reads the list of projects and options from that file. Otherwise,
    it uses the options given from the command line, or defaults.

    Jzbuild will download and use the Coffeescript compiler to seemlessly
    handle files ending in ".coffee".

    [files]

        If no filenames are given and no makefile is present, Jzbuild will
        run jslint on all files matching the pattern "*.js" in the current
        folder.

    [projects]

        If a makefile is present, the names given on the command line refer to
        projects in the makefile.

    --out <output>
   
        Specifies output file name. If an output file is given, the makefile is
        ignored. This option is called "output" in the makefile.

    --prepend <filename>
        
        Specifies a file for prepending. The include path will be searched for
        the file, and it will be prepended to the output. This option may be
        specified multiple times. This option is ignored if a makefile is
        resent. 

    -I<path>

        Specifies a folder to be searched for included files. This option may
        be specified multiple times. The current folder is always in the
        include path. This option is ignored if a makefile is present.

    --compiler

        Specifies the compiler to use. This option is ignored if a makefile is
        present. Valid options are VALID_COMPILERS. If you do not have the
        given compiler, it will be downloaded.

    --release
        
         Specifies that we should use a advanced compilation options, such 
         as minification, if available.

    clean
        
        If the word "clean" is given as an option, the output file is erased
        instead of created, and JSLINT is not run.

MAKEFILE FORMAT

    When jzbuild starts, it runs in one of two modes --
        
        1. If the '--out' option is not specified, it searches the current
           folder for a file named "MAKEFILE_JZ". If it is found, the settings
           are processed as described below.

        2. If the "--out" option is given, or MAKEFILE_JZ is not found, then it
           builds a list of input files from '*.js', excluding any common
           javascript libraries such as jquery. 

    The makefile is formatted in Lazy JSON. This is exactly like JSON, except
    that quotes and commas are optional. The Makefile consists of a single
    object whos keys are project names. For example:

        {
            release: {
                input: [ foo.js bar.js ]
                include: [ ../shared ]
                output: foo-compressed.js
                compiler: closure
            }

            yui {
                base: release
                output: foo-yui-compressed.js          
                compiler: yui
            }
        }

    The above defines two projects named "release", and "yui". The release
    project consists of foo.js and bar.js, as well as any files that they
    include. The include path searched is the current folder as well as
    "../shared".

    The yui project specifies "base: release". That means that it inherits any
    unset properties from the project named "release".

    Here is a list of valid options for a project:

        input
            A string or array of files that will be compiled together, along
            with any files they include.

        output    
            The output filename. If none is given, the compiler will not run.
            Only JSLINT checking will be performed.

        include
            A single string, or array of strings that specify the paths to
            search when looking for input files, or the files that they
            include. The current folder is always part of the include path.

        compiler
            The name of the compiler to use. Valid compilers are
            VALID_COMPILERS. The default is "cat"

        compilerOptions
            Compiler options to use. Jzbuild contains suitable defaults for
            each compiler. But they can be overridden. 

        base
            Specifies another project from which to inherit the above settings.

        prepend
            A single string, or array of strings specifying the names of files
            which are prepended to the output. No error checking is performed
            on these files, and they are not compiled.

""".replace("VALID_COMPILERS",
    ",".join(VALID_COMPILERS)).replace("MAKEFILE_JZ", MAKEFILE_NAME)

# Make these variables global, and set them later.
JSLINT_RHINO = ""
JSLINT_WSH = ""
CLOSURE_EXTERNS = ""

# Keep temporary files here so they are not deleted until program exit.
# There are problems with using NamedTemporaryFile delete=True on windows, so
# do it manually.
TemporaryFiles = []

def cleanupBeforeExit():
    for temp in TemporaryFiles:
        if os.path.exists( temp.name ):
            temp.close()
            os.unlink( temp.name )

atexit.register( cleanupBeforeExit )


class LazyJsonParser:
    """This class parses Lazy JSON. Currently it does not take advantage of
       python language features such as generators or regular expressions. It
       is designed to be a reference decoder that is easily portable to other
       languages such as Javascript and C.
    """

    class Token:
        def __init__(self, type, start, length):
            self.type = type
            self.start = start
            self.length = length

        def getText( self, text ):
            return text[self.start:self.start + self.length]

    def __init__(self, text):
        self.text = text
        self.pos = -1

        # Possible token types
        self.TOKEN_EOF = -2
        self.TOKEN_ERROR = -1
        self.TOKEN_LEFT_BRACE = 0
        self.TOKEN_RIGHT_BRACE = 1
        self.TOKEN_LEFT_BRACKET = 2
        self.TOKEN_RIGHT_BRACKET = 3
        self.TOKEN_STRING = 4
        self.TOKEN_COLON = 5

        # Possible values of STATE
        self.STATE_START = 0
        self.STATE_WHITESPACE = 1
        self.STATE_SLASH = 2
        self.STATE_SLASH_SLASH = 3
        self.STATE_SLASH_STAR = 4
        self.STATE_SLASH_STAR_STAR = 5
        self.STATE_STRING = 6
        self.STATE_SQUOTED_STRING = 7
        self.STATE_SQUOTED_STRING2 = 8
        self.STATE_SESCAPE = 9
        self.STATE_DQUOTED_STRING = 10
        self.STATE_DQUOTED_STRING2 = 11
        self.STATE_DESCAPE = 12

        self.ACTION_SINGLE_CHAR = 1
        self.ACTION_SUBTRACT_1 = 2
        self.ACTION_SUBTRACT_2 = 4
        self.ACTION_STORE_POS = 8
        self.ACTION_TOKEN = 16 
        self.ACTION_ERROR = 17

        # Represents any character in the state machine transition table.
        self.ANY = ''

        # Represents whitespace in the state machine transition table.
        WS = "\n\r\t ,"

        # There are better ways of writing a tokenizer in python. However, I
        # wanted a parser for Lazy JSON that is easily portable to other languages such as C.
        self.fsm = [
            # in state, when we get this char, switch to state, perform these actions, action data
            [ self.STATE_START,                '{', self.STATE_START,            self.ACTION_SINGLE_CHAR, self.TOKEN_LEFT_BRACE ],
            [ self.STATE_START,                '}', self.STATE_START,            self.ACTION_SINGLE_CHAR, self.TOKEN_RIGHT_BRACE ],
            [ self.STATE_START,                '[', self.STATE_START,            self.ACTION_SINGLE_CHAR, self.TOKEN_LEFT_BRACKET ],
            [ self.STATE_START,                ']', self.STATE_START,            self.ACTION_SINGLE_CHAR, self.TOKEN_RIGHT_BRACKET ],
            [ self.STATE_START,                ':', self.STATE_START,            self.ACTION_SINGLE_CHAR, self.TOKEN_COLON ],
            [ self.STATE_START,                 WS, self.STATE_WHITESPACE,       0 ],
            [ self.STATE_START,                '/', self.STATE_SLASH,            0 ],
            [ self.STATE_START,                '"', self.STATE_DQUOTED_STRING,   0 ],
            [ self.STATE_START,                "'", self.STATE_SQUOTED_STRING,   0 ],
            [ self.STATE_START,           self.ANY, self.STATE_STRING,           self.ACTION_STORE_POS | self.ACTION_SUBTRACT_1 ],
            [ self.STATE_WHITESPACE,            WS, self.STATE_WHITESPACE,       0 ],
            [ self.STATE_WHITESPACE,      self.ANY, self.STATE_START,            self.ACTION_SUBTRACT_1 ],
            [ self.STATE_SLASH,                '/', self.STATE_SLASH_SLASH,      0 ],
            [ self.STATE_SLASH,                '*', self.STATE_SLASH_STAR,       0 ],
            [ self.STATE_SLASH,           self.ANY, self.STATE_STRING,           self.ACTION_SUBTRACT_2 | self.ACTION_STORE_POS ],
            [ self.STATE_SLASH_SLASH,         '\n', self.STATE_START,            0 ],
            [ self.STATE_SLASH_SLASH,     self.ANY, self.STATE_SLASH_SLASH,      0 ],
            [ self.STATE_SLASH_STAR,           '*', self.STATE_SLASH_STAR_STAR,  0 ],
            [ self.STATE_SLASH_STAR,      self.ANY, self.STATE_SLASH_STAR,       0 ],
            [ self.STATE_SLASH_STAR_STAR,      '/', self.STATE_START,            0 ],
            [ self.STATE_SLASH_STAR_STAR, self.ANY, self.STATE_SLASH_STAR,       0 ],
            [ self.STATE_STRING,        "[]{}:"+WS, self.STATE_START,            self.ACTION_TOKEN | self.ACTION_SUBTRACT_1, self.TOKEN_STRING ],
            [ self.STATE_STRING,          self.ANY, self.STATE_STRING,           0 ],
            [ self.STATE_DQUOTED_STRING,  self.ANY, self.STATE_DQUOTED_STRING2,  self.ACTION_STORE_POS | self.ACTION_SUBTRACT_1 ],
            [ self.STATE_DQUOTED_STRING2,     '\n', self.STATE_DQUOTED_STRING2,  self.ACTION_ERROR, "Newline in string"],
            [ self.STATE_DQUOTED_STRING2,     '\\', self.STATE_DESCAPE,          0 ],
            [ self.STATE_DQUOTED_STRING2,      '"', self.STATE_START,            self.ACTION_TOKEN, self.TOKEN_STRING ],
            [ self.STATE_DQUOTED_STRING2, self.ANY, self.STATE_DQUOTED_STRING2,  0 ],
            [ self.STATE_DESCAPE,         self.ANY, self.STATE_DQUOTED_STRING2,  0 ],
            [ self.STATE_SQUOTED_STRING,  self.ANY, self.STATE_SQUOTED_STRING2,  self.ACTION_STORE_POS | self.ACTION_SUBTRACT_1 ],
            [ self.STATE_SQUOTED_STRING2,     '\n', self.STATE_SQUOTED_STRING2,  self.ACTION_ERROR, "Newline in string"],
            [ self.STATE_SQUOTED_STRING2,     '\\', self.STATE_SESCAPE,          0 ],
            [ self.STATE_SQUOTED_STRING2,      "'", self.STATE_START,            self.ACTION_TOKEN, self.TOKEN_STRING ],
            [ self.STATE_SQUOTED_STRING2, self.ANY, self.STATE_SQUOTED_STRING2,  0 ],
            [ self.STATE_SESCAPE,         self.ANY, self.STATE_SQUOTED_STRING2,   0 ],
        ]

        # One previous token is allowed to be unshifted back. Store that token here.
        self.unshifted = None

    def unshift(self, token):
        self.unshifted = token

    def next(self):
        """Get the next token. Returns an object with the type, start, and
           length of the token in the text."""

        # Return the unshifted token if there is one.
        if self.unshifted != None:
            token = self.unshifted
            self.unshifted = None
            return token

        state = self.STATE_START
        storedPos = 0

        while 1:
            self.pos = self.pos + 1
            #print "%c: %d" % (self.text[self.pos], state)

            if self.pos >= len(self.text):
                if state == self.STATE_START:
                    return LazyJsonParser.Token(self.TOKEN_EOF, self.pos, 0)
                else:
                    return LazyJsonParser.Token(self.TOKEN_ERROR, self.pos, 0)

            for transition in self.fsm:
                if transition[0] == state and (transition[1] == self.ANY 
                        or self.text[self.pos] in transition[1]):
                    originalPos = self.pos    

                    if transition[3] & self.ACTION_STORE_POS:
                        storedPos = self.pos

                    if transition[3] & self.ACTION_SUBTRACT_1:
                        self.pos -= 1

                    if transition[3] & self.ACTION_SUBTRACT_2:
                        self.pos -= 2

                    if transition[3] & self.ACTION_SINGLE_CHAR:
                        return LazyJsonParser.Token( transition[4], originalPos, 1 )

                    if transition[3] & self.ACTION_TOKEN:
                        pos = self.pos
                        return LazyJsonParser.Token( transition[4], storedPos, originalPos -
                                storedPos )

                    if transition[3] & self.ACTION_ERROR:    
                        self.error( LazyJsonParser.Token( self.TOKEN_ERROR,
                                    originalPos, transition[4] ) )

                    state = transition[2]
                    break
            else:
                return LazyJsonParser.Token( self.TOKEN_ERROR, self.pos, 1 )

    def unescape( self, str ):
        """Unescape JSON string"""

        ret = ""
        i = 0
        while i < len( str ):
            if i < len( str ) - 1 and str[i] == '\\':
                i += 1
                if  str[i] == 'b':
                    ret += '\b'
                elif  str[i] == 'f':
                    ret += '\f'
                elif  str[i] == 'n':
                    ret += '\n'
                elif  str[i] == 'r':
                    ret += '\r'
                elif  str[i] == 't':
                    ret += '\t'
                else:  
                    ret += str[i]
            else:
                ret += str[i]
            i += 1    
        return ret

    def parse( self ):
        """ Parse a single item, which may contain other items """

        token = self.next()
        if token.type == self.TOKEN_EOF:
            return None

        if token.type == self.TOKEN_LEFT_BRACE:
            # Parse a list of string : item, followed by brace
            value = {}
            while 1:
                token = self.next()
                if token.type == self.TOKEN_RIGHT_BRACE:
                    break
                elif token.type == self.TOKEN_STRING:
                    key = self.unescape(token.getText(self.text))
                else:
                    self.error( token, "Expected a string" )

                token = self.next()
                if token.type != self.TOKEN_COLON:
                    self.error( token, "Expected ':'" )

                value[key] = self.parse()    

        elif token.type == self.TOKEN_LEFT_BRACKET:
            # Parse list of strings followed by bracket
            value = []
            while 1:
                token = self.next()
                if token.type == self.TOKEN_RIGHT_BRACKET:
                    break
                elif token.type < 0:
                    self.error( token, "Expected ']'" )
                self.unshift( token )    
                item = self.parse()
                value.append( item )

        elif token.type == self.TOKEN_STRING:
            # Just a string.
            value = self.unescape(token.getText(self.text))

        else:    
            self.error( token, "Expected: '{', '[', or string" )

        return value    

    def error( self, token, message ):
        line = 1
        pos = 1
        for i in range( token.start ):
            if self.text[i] == '\n':
                line += 1
                pos = 1
            else:
                pos += 1
        raise Exception( "Error on line %d:%d: %s" % (line, pos, message) )    

def ParseLazyJson( text ):
    """Wrapper for LazyJsonParser class that transforms Lazy JSON or JSON text
       into a python object."""
    return LazyJsonParser(text).parse();

# Global variable to say whether we are on windows.
IsWindows = platform.system() == "Windows"

def ReplaceSlashes(list):
    """Transform unix style slashes into the path separator of the system that
       we are running on"""

    if os.path.sep == '/': return list
    newList = []
    for item in list:
        newList.append( item.replace( "/", os.path.sep ) )
    return newList
            

class DependencyGraph:
    """ Represents a dependency graph. A dependency graph contains items that
    depend on other items. After adding all of the nodes, you can call the
    walk() method to get a list of the items in topological order.
    """
    def __init__(self):
        self.nodes = {}

    def addDependency(self, child, parent):
        """Add a dependency to the graph. The child and parent nodes are added to
        the graph if not already present. Then, the child depends on the
        parent. It is not necessary to call the addNode() method to add the nodes
        first.
        """
        child = self.__getNodeFor( child )
        parent = self.__getNodeFor( parent )

        if not self.__find( child, parent ):
            parent.children.append( child )
            child.parents.append( parent )
            return True
        else:
            return False

    def __find( self, parent, node ):
        """Searches the parent for the given node, and if found, returns True
        """
        if parent == node: return True
        for child in parent.children:
            if self.__find( child, node ):
                return True
        return False        

    def addNode( self, data ):
        """Adds a single node to the graph with no dependencies. Dependencies may
        be added afterward using the addDepenency() method. If no dependencies are
        added, then the node will appear early in the topological sort.
        """

        self.__getNodeFor( data )

    def walk( self ):
        """Returns the topological sort of the nodes.
        """

        L = []
        S = [n for n in self.nodes.values() if len(n.parents) == 0]        

        while len(S) > 0:
            n = S.pop()
            L.append( n )
            for m in n.children[:]:
                del n.children[n.children.index(m)]
                del m.parents[m.parents.index(n)]
                if len( m.parents ) == 0:
                    S.append( m )

        return [s.data for s in L]

    def __getNodeFor( self, data ):
        if data in self.nodes:
            return self.nodes[data]

        self.nodes[data] = self.__DependencyNode( data )
        return self.nodes[data]

    class __DependencyNode:
        """ Represents a node in the dependency graph. This class is used
        internally in the dependency graph. """

        def __init__(self, data):

            self.data = data
            self.parents = []
            self.children = []

class Analysis:
    """
    Analyses the javascript files and stores the result. The analysis includes
    a topological sort of included files as well as a list of exports.

    fileListIn specifies a list of files

    vpath is a list of folders in which to search for the files in the file list
    as well as any included files.
    """
    def __init__(self, fileListIn, vpath):
        graph = DependencyGraph()

        # Set of fully qualified paths that we have already processed.
        filesProcessed = {}

        # List of files awaiting processing
        filesToProcess = []

        self.exports = []

        includeRe_js = re.compile(r"""\/\/#include\s+[<"]([^>"]+)[>"]""")
        exportRe_js = re.compile(r"""\/\/\@export ([A-Za-z_\$][A-Za-z_0-9\.\$]*)""")

        includeRe_coffee = re.compile(r"""#include\s+[<"]([^>"]+)[>"]""")
        exportRe_coffee = re.compile(r"""#@export ([A-Za-z_\$][A-Za-z_0-9\.\$]*)""")

        self.vpath = vpath

        # contains named temporary files. They will be automatically deleted by
        # python when the Analysis goes out of scope.
        self.tempFiles = []

        def processFile( path ):
            """Given the full path to a file, open it and look for includes. For
            each include found, add it to the file list and update the dependency
            graph with the dependency.
            """

            contents = open( path, "r" ).readlines()
            graph.addNode( path )
            filesProcessed[path] = 1;

            if path.endswith(".coffee"):
                includeRe = includeRe_coffee
                exportRe = exportRe_coffee
            else:
                includeRe = includeRe_js
                exportRe = exportRe_js

            for line in contents:

                m = exportRe.search( line )
                if m:
                    self.exports.append( m.group(1) )

                m = includeRe.match( line )
                if not m: continue

                includedPath = self.__findFile( m.group(1) )

                if includedPath:
                    if includedPath not in filesProcessed:
                        filesToProcess.append( includedPath )
                    graph.addDependency( path, includedPath )
                else:
                    print 'Error: Could not find file "%s" included from "%s"' % \
                        (m.group(1), path )

        # Augment each file passed in with full path information.
        for name in fileListIn:
            path = self.__findFile( name )
            if path:
                filesToProcess.append( path )
            else:
                print "File not found: " + name

        # while the file list is not empty, remove and process a file.
        while len( filesToProcess ):
            processFile( filesToProcess.pop() )

        # spit out dependencies...
        self.fileList = graph.walk()

    def addFileToStart( self, filename ):
        """
            Add a file to the start. This is used to place the coffee script
            utilities at the top of the compiled output. It is different from
            prepended files because the contents are passed to the compiler,
            whereas prepended files are not.
        """
        self.fileList = [filename] + self.fileList

    def addContentToStart( self, contents ):
        temp = tempfile.NamedTemporaryFile( mode="wb", delete=False )
        temp.write(contents)
        self.tempFiles.append( temp.name )
        self.addFileToStart( temp.name )

    def prependFiles( self, fileNames ):
        """Search for each file in the vpath and prepend its path to the
           filelist returned by getFileList()
        """

        files = []
        for name in fileNames:
            path = self.__findFile( name )
            if path != none:
                files.append( path )
            else:
                print "File not found: %s" % name

        files.extend( self.fileList )
        self.fileList = files

    def __findFile( self, file ):
        # for each vpath entry,
        for path in self.vpath:
            # join it with the filename
            fullname = os.path.join(path, file)
            (base, ext) = os.path.splitext(fullname)

            # if it exists, return it.
            if os.path.exists( base + ".coffee" ):
                return base + ".coffee"
            elif os.path.exists( fullname ):
                return fullname

        else:
            return None

    def getFileList(self):
        return self.fileList

    def replaceFile(self, source, destination):
        for i in range(len(self.fileList)):
            if self.fileList[i] == source:
                self.fileList[i] = destination
                return

    def getExports(self):
        # keep track of exports already written.
        written = {}
        str = ""

        # for each export,
        for export in self.exports:

            if export in written: continue
            written[export] = 1
        
            # split into . components.
            names = export.split(".")

            if len(names) == 1:
                # one component. use window["name"] = name;
                str += 'window["%s"] = %s;\n' % (names[0], export )
            else:
                # more that one component. Only the last is exported.
                str += (".".join(names[:-1]) + 
                        '["%s"] = %s;\n' % (names[-1], export ) )

        return str        

    def getInputFilesEndingWith( self, extension ):
        return filter( lambda f: f.endswith( extension), self.fileList )


def RunJsLint(files, targetTime, options):
    """Run Jslint on each file in the list that has a modification time greater
    than the targetTime. Returns the number of files processed.

    If jslint is not available in the storage folder, then create it.
    """

    storagePath = GetStorageFolder()

    numProcessed = 0
    if IsWindows:
        # check if jslint-wsh exists in the same location as this script. if
        # not, create one.
        jslint = os.path.join( storagePath, "jslint-wsh.js" );
        if not os.path.exists( jslint ):
            print "%s not found. Creating." % jslint
            f = file(jslint, "wb")
            f.write(zlib.decompress(base64.b64decode(JSLINT_WSH)))
            f.close()

        for f in files:
            if os.path.getmtime(f) > targetTime and not f.endswith(".coffee"):
                print f + "..."
                os.system("cscript /Nologo \"" + jslint + "\" <\"%s\"" % f) 
                numProcessed += 1
    else:

        # Create the jslint-rhino file if it does not exist.
        jslint = os.path.join( storagePath, "jslint-rhino.js" );
        if not os.path.exists( jslint ):
            print "%s not found. Creating." % jslint
            f = file(jslint, "wb")
            f.write(zlib.decompress(base64.b64decode(JSLINT_RHINO)))
            f.close()

        # run the JSlint-rhino file on any files which are newer than the
        # target.        
        cmd = []
        cmd.extend(options.rhinoCmd)
        cmd.append( jslint )

        for f in files:
            if f.endswith(".coffee"): continue
            if os.path.getmtime(f) > targetTime:
                cmd.append(f);
                numProcessed += 1

        if numProcessed > 0:
            subprocess.call(cmd)

    return numProcessed

def CompileCoffeeScript( analysis, options, compiler, joined ):
    """
        For files that end in .coffee, compile them to .coffee.js if they are
        newer than the existing .js file.

        compiler is the name of the compiler that will be used.

        noJoin is specified when there is no output file. In that case, all the
        coffeescript files will be translated, but they will not be joined
        together later. That affects the options that we use.
    """
    anyCoffee = False

    closureMode = compiler == 'closure' or joined

    for filename in analysis.getFileList():
        (path, ext) = os.path.splitext(filename)
        if ext == ".coffee":
            destination = path + ".coffee.js"
            anyCoffee = True
            if not os.path.exists(destination) or \
               os.path.getmtime(destination) < os.path.getmtime(filename):
                RunCoffeeScript( filename, destination, closureMode )
            analysis.replaceFile( filename, destination )

    if anyCoffee:
        analysis.addContentToStart( COFFEESCRIPT_UTILITIES )

def DownloadProgram(url, fileInZip, outputPath):
    """Given a url to a zip file, a path to a file within that zip file, and an
       output file, it downloads the zip and extracts it to the given path.
       
       If the target file already exists it does nothing."""

    if not os.path.exists( outputPath ):
        print "%s not found! Downloading from %s" % (outputPath, url)

        url = urllib2.urlopen( url )
        dataFile = ""    
        while 1:
            data = url.read( 1024 )
            if data == "": break
            dataFile += data
            print "Read %d bytes\r" % len(dataFile),

        zip = zipfile.ZipFile( cStringIO.StringIO( dataFile ), "r" )    
        file(outputPath, "wb").write(zip.read(fileInZip))

    return True    

HaveCoffeeScript = os.path.exists( JCOFFEESCRIPT_PATH )

def DownloadCoffeeScript():
    global HaveCoffeeScript
    if not HaveCoffeeScript:
        print "Downloading JCoffeescript..."
        open(JCOFFEESCRIPT_PATH, "wb").write( urllib2.urlopen(JCOFFEESCRIPT_URL).read() )
        print COFFEESCRIPT_URL
        open(COFFEESCRIPT_PATH, "wb").write( urllib2.urlopen(COFFEESCRIPT_URL).read() )
        HaveCoffeeScript = True

def RunCoffeeScript( source, destination, closureMode ):
    DownloadCoffeeScript()
    commands = [ "java", "-jar", JCOFFEESCRIPT_PATH, 
        "--coffeescriptjs", COFFEESCRIPT_PATH ]

    if closureMode:
        # Add closure annotations
        commands.extend( ["--bare", "--noutil", "--closure"] )

    print "Compiling %s -> %s" % (source, destination)

    output = open(destination, "wb")
    process = \
        subprocess.Popen(commands, stdout=output, stdin=subprocess.PIPE)

    process.stdin.write( open( source, "rb" ).read() )
    process.stdin.close()
    process.wait()

def DownloadExterns():
    """Downloads Closure compiler externs files, if necessary."""
    for (extern,url) in EXTERNS.iteritems():
        path = os.path.join( GetStorageFolder(), extern )
        if not os.path.exists( path ):
            print "Fetching %s" % url
            file(path,"wb").write(urllib2.urlopen(url).read())

def RunCompiler(type, files, output, compilerOptions, prepend, exports):
    """Downloads and runs the compiler of the given type.

       type is a key to the compiler information in the global map COMPILERS
       
       files is the list of files to run the compiler on

       compilerOptions is the list of options to the compiler, specified before
       the input files

       prepend is the list of files to prepend to the output, without
       processing them by the compiler

       exports is extra code added to the end as input to the compiler and is
       intended to export names to the closure compiler.
       """
    compiler = COMPILERS[type]
    compilerFileName = os.path.join( GetStorageFolder(), 
        os.path.basename(compiler["filename"] ) )

    needsStdin = \
        "requiresStdin" in compiler and \
        compiler["requiresStdin"] == True
    
    DownloadProgram( compiler["download"], compiler["filename"],
            compilerFileName )

    print "Running %s compiler." % type

    cmdLine = [ "java", "-jar", compilerFileName ]
    cmdLine.extend( compilerOptions )
    if "requiredOptions" in compiler:
        cmdLine.extend( compiler["requiredOptions"] )

    if type == "closure":
        DownloadExterns()
        for extern in EXTERNS.keys():
            cmdLine.extend( ["--externs", os.path.join( GetStorageFolder(),
                        extern ) ] )
    
    if not needsStdin:
        for f in files:
            if compiler["inputOption"] != "":
                cmdLine.append( compiler["inputOption"] )
            cmdLine.append(f)

    if type == 'closure':
        exportFile = tempfile.NamedTemporaryFile(suffix=".js", delete=False)
        TemporaryFiles.append( exportFile )
        exportFileName = exportFile.name
        exportFile.write(exports)
        exportFile.flush()
        cmdLine.extend([ "--js", exportFileName])

    outputFile = file(output, "w")
    for f in prepend:
        print "Prepending %s" % f
        outputFile.write(file(f, "rb").read())

    outputFile.flush()

    for cmd in cmdLine:
        print cmd ,
    print

    if needsStdin:
        process = \
            subprocess.Popen(cmdLine, stdout=outputFile, stdin=subprocess.PIPE)

        for f in files:
            print "   Reading %s" % f
            process.stdin.write( open( f, "rb" ).read() )
        process.stdin.close()
        process.wait()
    else:    
        subprocess.call(cmdLine, stdout=outputFile)

def JoinFiles( files, outputFile ):    
    """Concatenates the contents of the given files and writes the output to
    the outputFile.
    """
    sys.stderr.write("Joining " + " ".join(files) + "\n" )
    output = file(outputFile, "wb")
    for inputName in files:
        output.write(file(inputName, "rb").read())

def GetKey( projects, name, key, makeArray=False ):
    """Returns the key of the project, following any bases"""

    # Keep track of bases already encountered.
    bases = { name: 1 }
    project = projects[name]

    while 1:
        if key in project:
            if makeArray and isinstance(project[key], str):
                return [ project[key] ]
            else:
                return project[key]
        
        if "base" in project:
            base = project["base"]
            if base in bases:
                raise "Circular dependency encountered. %s depends on %s" % (
                    name, base )
            if base not in projects:
                raise "Cannot find project %s, referred to by project %s" % (
                    base, name )

            name = base

            bases[name] = 1
            project = projects[name]
        elif makeArray:
            return []
        else:    
            return None

def InstallRhino(outputPath):
    return DownloadProgram(
            "ftp://ftp.mozilla.org/pub/mozilla.org/js/rhino1_7R2.zip",
            "rhino1_7R2/js.jar", outputPath)

def CheckEnvironment(projects, names):
    """Determine if the program will run, by checking the system for all
    required files.
    """
    okay = True
    needJava = False
    haveJava = False
    haveRhino = False
    needRhino = not IsWindows
    needJava = needJava or (not IsWindows)

    # Check if any projects use the closure compiler. If so, we need java
    for name in names:
        compiler = GetKey( projects, name, "compiler" )
        if compiler == None: compiler = "cat"
        if compiler == "closure": needJava = True

    if IsWindows:
        # We need java to run. Search the path for it.
        path = os.environ["PATH"].split(";")
        if needJava:
            for folder in path:
                java = os.path.join(folder, "java.exe")
                if os.path.isfile( java ):
                    haveJava = True
                    break

            if not haveJava:
                print "Cannot find Java. Please install it from www.java.com."
                os.system("start http://www.java.com")
                okay = False
    elif needJava:
        path = os.environ["PATH"].split(":")
        for folder in path:
            java = os.path.join(folder, "java")
            if os.path.isfile( java ):
                break
        else:
            print "Java is not installed on this system. Please install " + \
                  "the default-jre or openjdk-6-jre or sun-java6-bin package or equivalent."
            okay = False     

    return okay

def CreateProjects(options):
    """No Makefile.jz exists. Automatically create one based on the files in the
       current working folder and the given options."""

    input = options.input
    if len(input) == 0:
        input = ["*.js"]

    files = []
    for infile in input:
        list = glob.glob(infile)
        if len(list) == 0:
            print "Error: Could not find '%s'" % infile
        for file in list:
            if file in NEVER_CHECK_THESE_FILES:
                print "Ignoring library file '%s'" % file
            elif options.output != file:
                files.append( file )

    projects = { 
        "release": {       
            "input": files,
            "include": options.include
        }
    }

    if options.output:
        projects["release"]["output"] = options.output
        projects["release"]["compiler"] = options.compiler
       
        if options.compiler != "cat":
            if options.release and \
                "releaseOptions" in COMPILERS[options.compiler]:

                projects["release"]["compilerOptions"] = \
                    COMPILERS[options.compiler]["releaseOptions"]

            else:
                projects["release"]["compilerOptions"] = \
                    COMPILERS[options.compiler]["defaultOptions"]


    return projects

class Options:
    """ Parse arguments to the script file """

    def __init__(self):
        self.names = []
        self.input = []
        self.include = []
        self.clean = False
        self.help = False
        self.output = None
        self.prepend = [];
        self.makefile = MAKEFILE_NAME
        self.compiler = 'cat'
        self.release = False
        
        i = 1
        args = sys.argv;
        while i < len(args):
            if args[i] == 'clean':
                self.clean = True
            elif args[i] == '-?' or args[i] == '--help' or args[i] == "/?":
                self.help = True
            elif args[i] == '--out':
                if i == len(args)-1:
                    print "Error: --out requires an argument."
                    sys.exit(-1)
                else:
                    self.output = args[i + 1];
                    i += 1

            elif args[i] == '-f':
                if i == len(args)-1:
                    print "Error: --f requires an argument."
                    sys.exit(-1)
                else:
                    self.makefile = args[i + 1];
                    i += 1

            elif args[i] == '--prepend':
                if i == len(args)-1:
                    print "Error: --prepend requires an argument."
                    sys.exit(-1)
                else:
                    self.prepend.append( args[i + 1] );
                    i += 1

            elif args[i] == '--compiler':
                if i == len(args)-1:
                    print "Error: --compiler requires an argument."
                    sys.exit(-1)
                elif args[i+1] not in VALID_COMPILERS:
                    print "Error: --compiler must be one of %s" % (
                        ",".join(VALID_COMPILERS) )
                    sys.exit(-1)
                else:        
                    self.compiler = args[ i + 1]
                    i += 1

            elif args[i] == '--release':
                self.release = True

            elif args[i].startswith('-I'):
                # Set the include path
                self.include.append( args[i][2:] )

            elif args[i].startswith('--'):
                # Allow the user to specify a compiler without writing
                # "--compiler" first.
                for compiler in VALID_COMPILERS:
                    if "--" + compiler == args[i]:
                        self.compiler = args[i][2:]
                        break
                else:
                    print "Error: Unknown option %s" % (args[i])
                    sys.exit(-1)

            else:
                self.names.append( args[i] )

            i += 1

        if self.output != None or not os.path.exists( MAKEFILE_NAME ):
            # No makefile mode. All the project names were actually filenames.
            self.input = self.names
            self.names = []

        # We need rhino.
        if not IsWindows:    
            haveRhino = False
            for folder in os.environ["PATH"].split(":"):
                rhino = os.path.join(folder, "rhino")
                if os.path.isfile( rhino ):
                    haveRhino = True
                    self.rhinoCmd = [rhino]
                    break

            if not haveRhino:
                rhino = os.path.join(GetStorageFolder(), "rhino.jar")

            if not haveRhino:
                InstallRhino(rhino)
                self.rhinoCmd = ["java", "-jar", rhino]    

def main():
    options = Options()

    if options.help:
        print MAN_PAGE;
        sys.exit(0)

    # Parse the json
    if not os.path.exists( options.makefile ) or options.output != None:
        if not os.path.exists( options.makefile ):
            print "Could not find %s. Running jslint on input files." % options.makefile 
        projects = CreateProjects(options)
    else:    
        projects = ParseLazyJson(file(options.makefile, "rb").read())

    if len(options.names) == 0:
        if len(projects) == 1:
            options.names = projects.keys()
        else:
            print "Please specify a project to load. Valid projects are:"
            print " ".join(projects.keys())

    for name in options.names:
        if name not in projects:
            print "Error: Cannot find project '%s'" % (
                name )
            sys.exit(-1)    

    if not CheckEnvironment(projects, options.names):
        sys.exit(-1)

    # Look for Makefile.json in current folder. For each process,
    for name in options.names:
        if name in projects:
            project = name

        if options.clean:
            print "Cleaning %s..." % ( name )
        else:    
            print "Building %s..." % ( name )

        output = GetKey( projects, name, "output" )
        if output == None:
            print "Warning: project %s missing output file. We will only run jslint." % (
                name )

        compiler = GetKey( projects, name, "compiler" )
        if compiler not in VALID_COMPILERS:
            if output != None:
                print "Warning: Project missing 'compiler' option. Using 'cat'"
            compiler = 'cat'

        input = GetKey( projects, name, "input", True )
        if input == None:
            print "Warning: project %s missing input file. skipping." % (
                name )
            continue

        compilerOptions = GetKey( projects, name, "compilerOptions" )
        if compilerOptions == None:
            compilerOptions = []

        include = GetKey( projects, name, "include", True )
        include.append("")

        prepend = GetKey( projects, name, "prepend", True )

        # Check for dangerous mistake. Is the output file part of the input?
        if output in input:
            print "Error: Output file %s same as input! Skipping project." % (
                output )
            continue


        # Normalize the slashes in the path names.
        input = ReplaceSlashes(input)
        include = ReplaceSlashes(include)

        # Process included files to obtain a complete list of files.
        analysis = Analysis(input, include)

        # if we are asked to clean, then simply delete the output file
        if options.clean:
            filesToDelete = []
            if output != None:
                filesToDelete.append( output )

            # also delete the .js files generated from coffeescript
            for coffeeFile in analysis.getInputFilesEndingWith(".coffee"):
                filesToDelete.append( coffeeFile + ".js" )

            for filename in filesToDelete:
                try:
                    os.unlink( filename )
                    print "Deleted %s" % filename
                except:
                    pass

            continue

        # Also process prepended files
        prependedFiles = Analysis( prepend, include ).getFileList()

        if compiler == 'closure':
            exports = analysis.getExports()
        else:
            exports = ""

        # Get the file time of the output file, if it exists.
        targetTime = 0
        try:
            targetTime = os.path.getmtime(output);
        except:
            pass

        RunJsLint( analysis.getFileList(), targetTime, options )
        CompileCoffeeScript( analysis, options, compiler, output != None )

        if output != None:
            if compiler != "cat":
                RunCompiler( compiler, analysis.getFileList(), output, 
                        compilerOptions, prepend, exports)
            else:
                print "Creating %s" % output
                completeList = []
                completeList.extend( prepend )
                completeList.extend( analysis.getFileList() )
                JoinFiles( completeList, output)

# Here is jslint in case they don't have it.
JSLINT_RHINO = """
eJzsvXt/27ixMPx/PgXtbSM5kWQne+mpEyf15tJ1T25vnHTbY3vzUBJlMaFIhaR82U3OZ39nBheCuJC
g7GTb3yl2Y/EyBAaDwWAwGAy2t4P3RRKn5eh9cWN7O7i7c2dnuPPdcOeHGze2b914lC0v8/h0Xgb9yR
a83LkbPM5Wp0lYBI/ybPJhluXTIOifn5+P/nb4DLOZZIutGzdeRfkiLoo4S4O4COZRHo0vg9M8TMtoO
ghmeRQF2SyYzMP8NBoEZRaE6WWwjPICPsjGZRincXoahMEEygfIG+UcsimyWXke5hEAT4OwKLJJHEJ+
wTSbrBZRWoYlljeLk6gI+uU8CjYP+RebW1TINAqTIE5v4DvxKjiPy3m2KoM8Kso8nmAeAwCaJKsp4iB
eJ/Ei5iXg50SUAjK9sSqgBojnIFhk03iGvxFVa7kaJ3ExHwTTGLMer0p4WODDSZTiV1CP7SwPiihJMI
c4Km4AVVTsCAZRXyJBS04iLDc4n2eLGixSerbKUygyom+m2Y0ioxLfR5MSnyD4LEuS7ByrNsnSaYw1K
nZv3HgDr8JxdhZRXVibp1kJqDIUsAGWVavyV8U8BNzHEScYlBunATy6waoTYO1W46KEho+B9sssp/IC
rZojVr6sicwWiDsFjPPgr1kGjAOlBk/O4gThf3oSHL58+ubn/ddPgoPD4NXrl38/ePzkcbC5fwj3m4P
g54M3P718+yYAiNf7L978M3j5NNh/8c/gvw9ePB4ET/7x6vWTw8Pg5esbB89fPTt4As8OXjx69vbxwY
u/Bj/Cdy9evgmeHTw/eAOZvnkZYIE8q4Mnh5jZ8yevH/0Et/s/Hjw7ePPPwY2nB29eYJ5PX74O9oNX+
6/fHDx6+2z/dfDq7etXLw+fQPGPIdsXBy+evoZSnjx/8uLNCEqFZ8GTv8NNcPjT/rNnWNSN/beA/WvE
L3j08tU/Xx/89ac3wU8vnz1+Ag9/fAKY7f/47AkrCir16Nn+wfNB8Hj/+f5fn9BXLyGX1zcQjGEX/Pz
TE3yE5e3D/4/eHLx8gdV49PLFm9dwO4Bavn4jP/354PDJINh/fXCIBHn6+uXzwQ0kJ3zxkjKB7148Yb
kgqYNaiwAI3r89fCIzDB4/2X8GeR3ix1hFATy6cWubpE0ACcTIARACuC0MTpNsDFwzW6XULYFUwMXhB
+Cr8hy6RJiHi6iEHgHsEPB0FubB4vJ1VKySMtjjufWLbJVPoDNlS8xn6x6DR5abxXlRVllhuRH0eLgK
A+y00E2A+0Jg6jwPURTxpwUgMwugRyKilBt7PsBn5zHj3mKZwB30lt5x2sN8esd5T/3QzBa/p+zwdVG
AXMO+F5ZBFE7mAqM8WoK0AokHHSmNQDSl0Yhqw+oZTCBjKJ7h9bfwLDyc5PESaBddlAPE46c3z59Vd2
Hw31k6C8erJCzhFp+PKgoVEcqJOokgf0ZKaJ2MSReoAntUgGSKAVf4qsyzBPs55ZWB9GDyE0BZu4yC5
1lRCmEgPkcBMM6yJApBMCEKl/QIJQL88rx44Sia5iEIrRCE+yzERj8LkxWNLrMwKSJeEUbyyTyafACa
raDenM/yqASRCQyVr4CGL7Hlz2OUzXEp32kZ0e0guMxWROg4LZZIAF6lKM+znAT0LAbkcOjAyi3zbJx
EC2DViskFrMYJjKAFEZAPhJBDEcGwshgDt+8yTH6TPI/tz66IXOy+n0fQnDGQBlDZ2QqAhVi7lAwCbm
EQn2WrdCozwvE4nGAbs4yq+3Vyy6MQh3OJFieBfB+dxdMoBXbl75HvGO4whlS588+CbDJZ5Xmk5B+eB
2q18X4RFUV4CvwTwaAR0ffTCKiYAFdGOETCuJuXSiahuOCZMHnAvpFAYw2IdwkNaqJBwZCZG0BTvTzo
seVchfosGS0EViuByYlNKgKDThCkK+gNQsxQG4SAdgR0AqnAO5SF04jHOCf/k/NvHn1cgeoDmT7lcjZ
4HeFAPeCNUMyz84K6H++oQh4XlA/TDiJFHNMjEMQFk1wl9mAYyFFEAatz4UQjO+8lTOAtQFrCMy704f
s4HKMqh7llJJJlJ2LtTVhi7wF+IYkW8qx4EaKxSSfhIPfH2fTygWXAoLzEgDFiefdJ6YumYsCANuFPs
FQUGQOsHdcIWRaiUQQgVDFLk0vWiIWT9lNoaRTvqwnInEgRoSABioDp1r0ClVSQceaA9xg/l9hjZn2J
dCXIaiXAKMe0OugpC0OmMHR3gyP5pP5eJOyvu8GLt89/fPJ6YLyVAsQNwqTEbnD4BlUi872QEgKiBvB
Z3p1UX0r21LFPgT/tBblrgf3K/ob4XS8CkwXPk/qnkyQroA3W+xgafL0Po4tJROPmep/DSBatWfIqxd
6+3rdMHKz3bRKOI+9PbazECjcYSftc+YAN0btaR2Hwgo3kq8/Vd4xCHv3NzcNUYYWP2zsKl7hfudRV3
oWg70k4/Pjy5bMn+y/U8fHJYllesgGtYEIXJ4fKTBRkJJtWMPsGfQTCBPiBCe40g7FyV2hzoEdTx+K3
eXQaXSzlLbMMsC95rlwZCzaPxzDX3Dwu6W9Kf2f0N8e/G3vsL/0cb+LfP8IfwmazP45O43QLH/bHIAg
/gOrC7lDygzrEbkgWs0vGkFtVDigcy3gWRxwA5RW/glbhV1m2lDljU7IrVmUlL5JoBXtZwASew51F+Z
iubuGf2/SH/g7pD/093pbZ3Mf7+1TfPf6Xfh7QH7zcf3y4/xTnlhPUKP/xkvRd/vk+Nugg+JHp/wOYZ
MKs9hGbv8BFmJ6FMEd6tCrKbLGfxouQ2Wtg/INmehyNVzADe8LzepLC9CnHOQ08QxrCD8wO+OXTcBop
OTwFys3hBwbDp3GUgJb1FPUZnpVQjQbBT1n53xFgeLAI0cbzt8OXLwbBsxd3dvDvXfjz8q93dp7Q713
4eb7/j3d/33/2VuD0/OCFuH8ellDg8yhdHZTRAq6yMxWhF0/+uv/m4O9P3h28eHrwgmbwL1bIczwnQb
aXSwb/6gD+vTw80L55lQHzD4LXYXoa8Zq/hu/gNhGVex3NQDeGMVa+P31yscTfIv5VRel1VgKdlQeH/
9/rN3fe3eX54B1cQ2NlSfJjCDkd8jnxYXmJpR1egj5zwUs5vCyo2m9oGop/96EL8KzexAus6JvLpUDq
7esDefVsEPz9R84pPwve+Dkawx/QJrPzQfCP588eI+dQZnDzU1kuXzNlC7n1GLgQigrHY8gvBHzTS8A
knE6fnEF3ehYDZimWD09A4yp4PuG0CGdokksi1I5DtOONkxUZ6ZAkiBwauqAY0N+QIcPlMokEgnQj+B
xvLulZDs2OOv3HVcj+LkDzTfFjIkeYn5Jxs8DLuMRv8jKeyMYLCxAB8HA1jTP8KbNJtsCC8OGvKzQhA
l3G4eTDac5mD6ybVk+GYVmGkzkWgl1UeTHJkizXnsXI95uWXJZZQcZEDR7U4ijEjMchStLxFLAcR9ES
/8bYg8bxKc9tHBcfV/SkZHPwcQL50E8KU/dpmCwyrMA4ydhj+Pm4ykqCXAmC4OVZnBGp4RraBFV+/Jt
PsU032cVwnJUgQzb1B7LSvIK1dwXysfnJeTwt58pjyCIJl0Wk51LRk90n0azUbq0wstxabvRGL5oMt/
q9vU7slV4l9lTPtliGE+jJehb6x2W2rN8Z1cFn1trgC71Ucc/IDL/YmHl2nrKfQsrCMSgVl+dkIh6vA
BYBLsuoeJO9PRAyaAL/g8gvGatMYD7L/kb8TmY24YPMJFzSHybqNvnVEPvbJr4oIgSCXoNf4kxnv2S/
jzIYWURHl1Mg9q7MI7ZgMId+mtCoBZdZET1CQombp3EiXzzNkmmFG4kV6P0oXennAMuHUY3fouAk+9Y
kiRF9mGlE/OfneHoq5Q89mQ7EVAQuFriKMaW1jIT+YAde0hUhli0WIfY+vIhSmY9YQ8AX6SzOKZu0yK
gCcEETTpYBYIrfwQWoFOUrGP7eZD89Paxyqh6/AtLgvBShc6pclqezJDsHXYS1H9wXcfJBcNEEhA0QY
gjaXx4JUSYeorEUH8ArRvE8XhSEMsr2ySovMkngS9Q6oJrTMP/AisIr/hiuTrE50jzjIKc0CLGrKEp5
Lnj/YR5+iNkrFJkw8rGbLAGlhwPTfY5Ds7iezGOecx5NldwKEn7sTRGFyvcFclGFKd1WWMFcH0QkSVO
Zl5COaCZgf5MYx8UplsxUqGmEvABjrnL5CMYV0Bll009Bii/j9MOArooPlxwJZoc9BFVhVdAtjGaPQL
uimwT/QMeNocxfJVLMRIevzghihnUDkAxRAY5OC+IwuOQ1i3P6E3GljOUSF8uEvT2DP5gPXxjEK+B9z
jpTuI8E00ak36Megvq8oHiEkwtgIPodTqIkKYB9QEUSRJGXClFQES8vaQEw+oj/iczIlAIPi+/xD8gR
LJG6bHTGvuQ2DrrCxxeDaraOl9EE/y6FIjJDBbXAJpzFp9R7adGTK1TQCaMxzFc+DJg1E36SLGQ/ks/
hGvoVV1NmQKeC/wgpMcsQs038Gc7CCUl5frOIk0spvukZ6okSAG+G4fQ96OjVM5B75WSu3KtDAD0ig1
9afXIe8aFslmUkPtGiW5Sc8+EmZj8LUaM8PGWNPWOKO/0U4pfqlOMogn8fcTENd6vJvIhDvBCtTwakg
bQjVVeQGTDkKZrkYIQCReYU2gWohUywKqMpV3Mpk9N5VpScvmzWJn4xlwwnGIooYWzN60Y/lxEu0/LM
5ncGwRxU6/m38O87+AecNP8B/oXFy/P0VY5rK8iw8yicsr9IsDlREH+TpciIC/U5dPgsxy+AeS+n0Tl
elaw3z/HTcgH4gviK36xSJCJKpWquyXOLOaWhW+KfBfYfYVTANXSxjo4g6ZTaBn8vXs7oApq7EnJ4f5
rh85jAliv6wXyK/WQ5D+kCtOZ4QpOP16s0ZettxeP4NBZCKS6eYg5YYvEihKlZfEb1fJ8hOswUMCCrw
iD4MIbCP0SXp0h0Lq4pkw/KctjfYZJPTEDGJP6TINqglZ4OyECIf6EnV8O0uAWBg5PKJDxPedsm4QXN
9OFqDO3AMgJFDv8CHoIaSQTSHsaC2YyKjtJTnCtugtgua9pYEuO/Mf6BpmbyjS75sMkyowc0gtGl5Dv
BY+wpRxCvGSPQpRh4qpyq4YfdCsHP7qrhh92XUZQo2jk9rMpdROyvzBAnPpv4M5yL/o937J0c7XG8qp
TP6k7OTtRnysRE/3pYwgQTi8iw3+BfPlDB1IJPcWkMAqkhx/BFKDoTTNROkas22YUyo+APhH7Pb6Vuz
u+Ztiyy+sBefID2zWYzprDAfYZIwORyMqf3FxVd6E6oyHAN44zM7SJBki2m36MzyhTFG/6sFur8kj1h
bcOuhfrBMqFHy1W+TCRA1fT8vtI9+IMlKtuqKsSeK2oIe8B0EOr+zJKGv+lqIFbw8IKoHZWyVy3iaVq
x+eYCSKgQA+4kMaCTo66HzQZtfZmTErwQI8Uim4D2ji23gLn3j5fs9w0In5TEWRqe0Z/wfcYFONzEp2
yCD5fwQRoJ0QxXNFFIMzHekGERfwo+8U9xZMm4uQaVa+h/MLNFqyPqgjwjup7m4RiNkfiPrWGuUsacc
E+TWZDXzAzCzHf4y4fvjEOy3EC0FqRhZanMAsUGDhMwXKTsL9lS8AKJTCv05CTBRwmWE9dChJ7Kfqnl
BL/Q0gD98A7Mr7R5p3gqO654INoN7knsQ2vkM5IQm+JyeFFlIx6hEgJYLsPplEaCTX6ldETxhPdEloF
4KPujeMA65JLYbxN/hiSrh+EM6qd8Ll+wJqJvQHxXwzndsk6Al7oSjs+UDrAMl+FlCKxGlcmRbeGHhk
v4hRkgU9/o+kCq30sQVLMQ1cUlaCFL9A9ZrmYzvMyhHzERzhTiZbJa0N8C/8FVJhoXrlbL59TxhJjEq
/OpUJaXOfsDajz9ckvhX5FBhDpaPca8cxphl3l2ykxncLVYsidlhvIWLvGWC5YljZDLC54XKM0fVzia
k2EHPgdum6LWxrkvD8/ROh+iOISfKZsp49XbPBnw1USeFxGXWfLxFzuB0G5hjghspFn78mjJumXO179
5LjBdOWNZYY9CecGuUGLAVZacRa/Ilours4vo7RKmVIT6PE4RhGlhLLOsuOQWjDy7DPnImCN+iNVqjJ
mv0kdisl1dH6Q/CjtZAeyaRDwbZpIUo3QRLpb4N51eyvdn0X7Bfl+pDcWymjAuFaKqINut+MWqsiusa
iX84Sqhvzk2A8sICA96Jj3mWnMRJSTxlNkejGqVvQJupLWiAFVH0Aj9DVg71fAt4ihNQ/wFekNrSb1D
GYQU7YNllZClsUBLLfwsyOhTpChZCmph4RgGGlVKf4lkS1LQyHtLZKSOa0U+wSUhsk0WfJqr6DlssYh
+MxRLhTIroOul1NeL1XjAHCSxQihy4Q8wIfYgvMIeJNmpuEwnIhs+1SvRQwJkFf0Ooa8DMTfxMWBZMr
NnCVxUUnuV0DyC/0syhDN5hgtNQ2igUzLd0h3O+ZmzlnzEFHh5W8zDaXa+WcujhD5a4IwMUYAHzIBd4
vwN/STIVwLHIfQ6KBHvkvQ/mDVL+pTZM7TxPCJbcZkJ212ZvV0uq8cgYb69ixcfsDlA1MPQjL9APyRk
KaqmyF0meEDMrYASq5TEGc5s2Gx8c5XGOKEfjuNpvDngy7E8l1V6ztSvFbXEC+QeXMQcMFcz/oNzGhq
Pz8SEgVEGbVowZUkkhXGun+EPM8KcxUU8jhMal3k550Am5n1TCrps0g0p/jjc0F2xgPrDNW9SGkTxB1
dAALnN8yyfGoZbeniehzjQXYbzLHuEPnHPMlJk6YF2Td2zNhllN7wvbP5KnHGxyZZFt4Ofo2C8ihPmE
xRW8zWcy0HN0alJuBkVGXMQOicnr+lqEjFXmRD6OC5PYXaaNxDz/JE5CGebOD0DWuDssyy4twv3A0Q/
HfiCOcZghjWUYC6TzEY3bmxCc/N+u3nvxg30qeH+gXtBX5bW3+JL4/ieLQa9Q/WHEmSNqLHW6BXB/mN
8D3PmkVzL5p8sUDwZn4DSfkkzELkmxIVyYWRwTqoBy4CtpY5OM7QF4MJKyozZarFpljLFtobp6QqEC5
SCr8jFGuEuF9mqqOwdSiZyoUpmwmso0cU+oTgmhWW+SiIgYN2dgKYj7JKvxNde96TBqWd7jbpXoH4t3
34eEPu9IU9J9Bdl/qaZ8EKDUWUFXMmdBMj7jLtARcGGBFbwH4PCYWDfu29Fq3d/z/58z/nc8WLD/cL+
/IHjsQP8tv3x0P74lv3xtv3xH3ttbSKcJiwtwjY4cG89bBRiLhwbo7LeKinAQLsEtQTF4EesAOJpXgr
nUuDROchZtTcRznJ5tUf3tnqxRaLq3gmTt8BUqyFOmB7ahXvN+UhFugGGtBPl3gbDx7VGGD60NcLUc7
F2zDoXcIGMXsPcz1v4fqsNDW9eco9wvRcyOagihO0fz0Rjc84CropgcgwK3rT2OV9fNj8XLyrRUefRE
Ac+PTO2EGlmRjwMmtg0zKcSiluAFQzZ3ApmwVONoZYazXm2K1SEaPWRObRWOdmwmxSFPZtHh4cB6AIf
QlqlVxEqoUXysNQyonUhW0b04hRQQk2YVt6KFpxokceWVZKdnqK3u/F50JdLitz3Iiono61armzJxZI
riFolR/S4jXMNo6j43k6lJ4ffo9pdhhctdcJ1G2sO2J9bvqWlDNu3OCjDG4Wwi1VR4loPTKHqWfC1Dy
MLYhHxtq1hyIJvQ4Re4F47UrSY8sSRgaxQm1wyuU1mi6KWqTB4m62Nnv70Su9mtE1Dw42Z2Sy4qVKVi
X2BF8DHJU08tazQPmerJvu8opENjyyVlxZK03oeaGIpzM/zNnIzA54lK1KCcWMPvpatjyOkojs3Zi1s
Q0bWJJTQ85x/X8CkKaBNk7jtgSyL9Yy4zchkCbHOvg1zRXblISyZMcZSZcRrZM8A+Yp/B7MkEE1JncH
IymJrEczzNb2M0rMY5uKEpLcEpkmiLd9qZ0KVBxAhAd6fio0nqF/WB2QxYBnyvKDNSgUwpRwlZjD/W+
W1AsTuVC1bPtszs31+yH3hiiFuT4pP44l/1VlROrJcdBJdaxMmyAYETFjPYiU3zdQRw30kaCOgPaCo3
rGtaWnGN9eSgmAdgmjSa8uSo8smxThDDnDmUTAfO41cNNWqsggUXvknzngDZiEp/IjFFVzRbnK/RojG
Lawgn74yycI2dWAF0YeGejlOnWLcNjuGaS9mdR6NZXYK26qKEX9rKkV170XhvFzXVpJVrt5bgWp+RY1
A3H7XkFNWKJpzA9C0BajmVeIE4v4ejTkxGd1SHC2ptALRgk8LkO4eYAXiy/HNOZHHcRtObKm4DYiP4Y
1AbG2sJSe2cNYCRBaGNsTlElsTUH1RzD4dYQtlamk2GLanrhmmzgR2GIZHMwxbLWiGWdVyssIso1S9t
xOIlvJagNi0qgWIrUC1AeFiTxtOlrUWBxxbXmnJjK28NAKxVY0WtNjChhdQC05iiaQZqFr6aARSRKoL
SMjApuJQr1OTFajuGC+BasObuIaZ5H7Jo1jgbsNB7U16WQclb1a+KbE+TG1Kt/lNDUGT5TdVb/rNNti
Pq7CeZTMsc4PYbIdFJ3ozYyssubT7wpK3uwFsh0VHeN98a97ymy2wFgwaYNmiRTvNaO3RF1/hu+3BD9
KB2wdWelu34yu9sX3yRc8qz7rVvZab20J4NGtZ22GZA7OOhR32MrQ0hR1WOD374CDcon1hpXvEpgdsH
l5654uy3qPdpE+2Jyx3+Nr0ga18upvbuPL3bufJyh/cDxZmJ178UHmT++Urlv3b5G/NF92jjeVavQes
XMj1gPWVUcJ93YvPKgf3dn5gTup+bSHd0tvxlW7dHvyreHe34qu4VbfDMmdpr7pJN2kPfCtn6XY6oBz
xlWcWmeOGtTSaG9aQOc2wbM28lb7CG9uHJ7m/tldbSGdrDzowR2w/vYScqz3pYJG9TljhP+1Dh5qvdY
t8kI7YHnRQXbDbZJ/0vvbJV7pnt/O69Nz2zVdz7d5shDUI4YY1Oc0Naw4uDbDG4NIAawjgBlhjcGmAF
a5bHrCe/Rhd2n1liXR/96Jv6i13LPpLAyz6mfv1ed2RfLMV1m98U13Q29pY9U33gzUYrQlW12KaYCvH
wM02WEOLaYCV7sHNsIpHfCsdhFO8B59Jr3kfWO5N7yOrFaf61j6Ejva+fYg71HvxOunqnn1I+uR70MG
i17fA+o3HljmAE7bmht4iU6WPugcONSd2j3wN7nXCCs/3dvkgPdx98I3ylS/v2JQoJ2yyWnjDSi96j7
rpkqwB1jLPc8MKd3MPmkl/dA9YxQO9tR9b5poNsMJxvZ1mlnlpEyx5p3vBkp+5J77ki+4Ja84f3bDmP
LoZ1py82GHTTJ9buGH1ka0J1lCh3LCl1RzlgI1spjYHLPMq96Ivcxn3azeL3HPCWmwPTljy8vYch8yp
cQss+Ya39yFTnW2DdfCDBNWWDH6kQB5sX3TtOe2BrYE+o5VL65qB9Cyto9SbLOzPI9fzC/vzOLU/Xzj
yWU4cz0vH8wubZ6xS95diw1v1lHnJGYv86P6m3NsX1FkgjlYg9KhrBnpcef25gchbsg2I7QIzgKwEYb
syTLfP3vEY6Ng7hh+NwMcle1EaL1L2IjVezNiLmfEiZy9y/cVmL6AXm/qLbf5i28jqmGUFv9Z68jgDM
nHHfApzm5bS10v7AJ7EuI0TyHOkdQcWy6U3QE7n0SPwhjmh4BVtXtfRpN2b+JbtesGrszCvUD7RUWaR
EATK+7bAsPIDEfpAqyP3i6EocxIWgw6Uoel0H+6Kq98+13HHAF679jcsqNeu5Q2L6WV7QwG6dm25gbj
i5VBIEN7L+SI5NDLuCg96xlcUqMtWEm6F2bXijXG8rG/GTipgZK1m7HDflYHeeJrtOjKMT11vZMytXf
NdNr3kaCglQ5vKvdEmCrmolIq5DkQRnWzNwiI17dZLRDSCJQaBCXB7h1lvHshpt/YV7aAzQSm6k7Xou
IzsnIf7yFxvEkFWRzsxLETsJRMd/mLXA3O2a7ReSdxhb0CK+D9mg06nsnWqPKaJmUOUONiFB/ax9AAW
3cdG2eksdeUW5843Z643iayD/qb0q120cOVAEYOsfVUE6DFpygL22OqNG5/sfMMC4Ni/yReOb3IK2Rq
4eU2ExTEqLF7sGv3Y+cn8jotG87vON98633znfPO9880Pzjcg++xiyagFxc2x0XnOu53lDWSk537LyN
hHzMVO+R7LxjTeLE4tEkUHwlg6BisYQIWjB30YT11vKHSODS8eeNn2hqLcaCJbhOgX3Yb3EqOBktjWZ
eOcCbYsCVZmo2LYmDUGRxjPHbXGGC32PodYuN6ULfoDISHHSRE7xEQr4pLAKCINXSJQ5Gr2Zxoq9SJE
2bvGoFrHUf+OBTixcUPmlMEi1EitLBY3wMxfjNoqrMjA+RFFFLEhtXR2Nx7YPXA3FlMUxcknepnLPHK
0hAiKYQ4LH53Y5EsX8fLS+WY1vrQzIsaHcLzhje6uNfEAqlXEAIwbmGgCdWuJpzYtw9SgBg8HYVEBWJ
PZ2oYCNVi5HItw4E+RHKy5URwG+xtyyA7qQwOJg0HglpXFauxo4GLlkhqkpVmrVEq9uVWpK20KWZmbc
Dz4gslnFIzBs7C5Z2FygG3PMl44VGOKAWFvCR0yt6FFxRElGT6soubHzi6zcnbAlVN60TTZ2qYU44G/
sU7942kxUD+AaTFtIIPnFQyLpDdQYA5qZ6QooCmLiaw8oHB78h4D3i0w3qF8gkvJhXKbZR9CCs8hH/G
4XNp98TJNLquHKbAai8NRPcpYfB75gEeQkvfVRhoZB+Gv+qEvHAD3xbDP1a/z6LSW2xnHQD5je8J0O4
ISitRupFIik9oBTqszfuwAGGqxEaDu5e8AYCg6LWmVz70VAOMnNRYh4iY1ArzNG/zUq7BEDgCMENSIQ
0VoFwDG4mnM4TKVreFwgac4MW4AHqlFBbB2VrJS1cN8CBsdM2BJSLEdT+e82kkHVlz4EQcN1anZYq0Q
1XkHLggWc78pDx5XvwHiZwumdrLlk+pLFi6JdsvJTfFyu1xZWQSVyA24UU7dH4dHWsHnTx493+coiJy
U3XEyc6MJqmrJZK0fP3qiHRDPnNAydIkVHizYG1BGFXYAyvDDbTmacYpdvFPbD9WQox6hwgkoj9poA5
THjrUB1qPdNgCKILCtOVKMWJ9a4zEfgQ8gHurhBcjO8vAAZELDA1DEB/QDpKCCLYDVoSFtgLUTRBoB8
WgRj8qwyF8+gNWZIs2A8iyRthzFSSOWou1yjoucdzz4jC55ngRmsi0TPntx1xPuzo4XHJ5A4wd3Z+dJ
O9yrg8BINjh+KIwXnF5jG5w8QqcNThyt0wJnHKzjqq9+mI6Ec7AB7kJ/V9eyefCQvdoMAWYryk1deab
AcpU+EeYpnQpLAyffve4eNqsN5nLcxKO12c52zKE/S+uHvW7xTEeqDkOltK08N1FYHIfjBVsdkdMKi+
fGWFCww9bP/2iEZcdK+eWrnNbhCStUbS9YOuyjFbY6zqM130cvn5sVc+WrnczhDSuO63DhUD+uqxEHt
vjvh2/tCK8W2OqEBI988SwwEwV7vtWhCR6wuVZ6Aw7iIDIf2FzbYd8Ay84v84PVIw40wfJI/36wlkD+
Tlg6gMAPB0vcfidskmnaRUO+i+n33rDiPDcvWPXEtxZYHq3bCweM+uyLL50P5wkro0X7wGqxov1g6w1
th+2Ar+Z01ATL4kz7wcoD9HzyVeJOt+dbO3CvJV8ZeNoDByUudRsO9TP+mvNVzECtONQiWTfDspjVgZ
FcsK8s/GOF1eJCNMHKUwx9cLBFrHbBJnYlxgq7ZIHTvPDFtQzffOuhpZthLWOmC7aKMN0Oiwc+WtB1w
uLhkF6weHKkZ74iALQXrAj+7AFrk9Mu2J+jsTfsuYW2znzJFOkHy07L9IatxQxpgtUCTLfD1sFaYWWc
lBpsbXYGk57gAudkGAlanDkfTkMYFsqMZlDSVZLOkad1cTSQgEoyoq8PSjqqfQ5yBuEp7hn2ml16i4l
MA/A7el/wZVTSNuV7zFPekLelvGPg1S12Yu1lQfOXOoiIIF/N2i7q884Ldi4m1X+VUvA5fm5fkOUBz1
IA0wR1+y+Tyaf7x9sPP7FiPx2f3CqOT+BRcWvj082k3I4Ham7iWEPFWFtApdMyuUSHsKjkizdphCUuM
Cgej1xWLVtNqOCj49UOpCH+3Jnh3z/N6ObPdBNO4e8P7P0PO9/B3z/twIs7fxp/R3+/P17d3dmZDOln
hn/v/hfd3KWbH3bo5ge4mUUz/Dub4SP4mZ1sU5VoCl5NyAmpX6Da/aP+1m+fj49Gg917vc3/PX54fPL
NX04+7e093Hv46Xi7f3yrzw6U+sSXxh5+4uczP/y0BwDwc3zr6Hh77wQubh/dxt/h0fEQf/8IWdw8uk
mvPh19wt8HDx4+wJzv9/GbjZNPxxv946NPwyHkc3/vIeb2Cxa8QeUfhcNf94f/8+4PJ/xqZ/hnuLn16
QguTm73jy7+cYKX4XC2P3x6cvvT8Yje3Np62D+Knpwc3T4enjxkwFsPtxgliPsZObZ5EmSZK2Tpbe49
ON6++Q1wR//h7vE2YvpwFxHdkoipaEFJAi+ozqcRlnb9+fI6KJxJwVOR1TmTphEwJRP52BUkDqmFD2/
e3zzePj7+2uxYoXT6L4LTKVGVxJbKHwLRjNHuwU1oNODbDeTxIWsJkJM5HslRzCV0QtDHt7Bt4YfBVe
fKSbiYcUXfxeVbf2Cfvg/PQi5yV3kiP3/PP3+4WwF8es9/o8lCPDrj4Sc/LTJgm0+425M92AJ+3BUSL
0+CcTgFXaGSXCsq4CZ060/YAPuPoXsdj6hOn/549Mu9k0/olP3Dd5/g40/RBWlbMMR8QmfbT4swTsqM
585Evsi3UHrDb7vf/HG0N3hw+/jo+OQv/a3NHmR7fAtFwB9AvKCI+WXv0//uSVHg6hr3ObXVbleoJf3
lm43N3ud7u8dDLJDK62/dendi6XMjljNmB3hMb2M/HcEvyiiQeKxVQhEorFB6oyz6I+OYX2SeIIneHW
8HXBqDXpFfqr2YwiArfhFT3lsBS+wNm71b9x+Mbu6irL699w3mIkHzC8OOSYy8C2JHW1siP079KXcQK
myPxRi8i7SsdI57rHQZqPcpnhrxmT2MZ0EfA7dnM76qM2In0gYbe3tBT3zS21JQrsPtVfn2sy2tZk9H
VWT4vSC7p00B6VCMNDpHjO6p+NLPDQ3tuHiXnad9cWoZ2pfV8nh2HDtZ7qi+RDfCsPj1PBzFgXIyjtO
oj4d/qeVgBOS0whZZoY9HiQRG7ZG2Amkoa0t/j6k8Sk+QNPBTp47ipCPwwx9mOlaqJ494rbWEhTC4GX
GkNQAdLtXfvgkSNejdDBfLe70tB8x9BpOUbpAHDOQUQThR7zmw5gdotuHcR6SDB8CJYS+4eZPqENyH2
1/ZUAB8+elTDZnqi/36F/8jvqgwc6FGh3f6o7ZTL+jP7UWIE5XcnUdtM0nf49/6R7/89hmGmuPPSOrq
23AQjHXuQj7NibXGJ9aOx7t9TuHoe0wr6QE9tRcprQr3gofwYDcIlX7a1sgUZFUnI8rTA3EUAS2DoJ9
XESTxhyiASY16oisApXgUD052ONLQMCFoUcXIzEcuQqUZXedZoshsPP2QneBWe4iGopQWosbh5ANpBr
X3KgoFur9dovqwZMGx2YFwATuwAFAjpF7CJzmd2QCfUeB3mItlopcQwtlsFqVTwrkaU+joF5zI0BCMc
1k02SirYCROLkZ4ThYxnyFPFKa5p0kP8X3q8T1uK7xdZz1Q/WrsZpNkyG8TaG6+VfIo1LhOoDCxfawU
PzE/+2w8EaiC4onI9nuokuJVOKqOu+9vjcR5Xf07P2xtjejQtf7wuy1N1G7Bh1BrG9EMmqigsodL0oQ
FmjVr8gLrvMEcBkfYvLZRgr8mH0EbecRYpLopMmDXoKHlTFt3fXNmwJ458xm0b94C3DN37r3mm7sA98
4djVf+mRN06zCN/fcVPzwMpAYL68yXzUcav6BjZH8xCJIBiAIVkXIOhNIQS2nLTY+dU0P+INq+WXSg3
YW8ag+liNkNVA9YTPxg291gAVy9GfQ34Qe9hUZ0LHu/nwTbzCl3xGJ4bwW3gjs7O9BdrB148490kAMQ
a2u0aVHnajXnBMHKg4aFAxiQAHhPV7Xw9DmgznlFdhw2SxynpKPvvVpnK0fxlA1dfZCyW6i7kpPk//v
fumUYs6l/XTUmbnMvR3QeCBS0U4FM5vQGD2zX3pwben083UUcsKG2tJbKw3OgurbMjO4RKW4YIJofJc
EwuHOCpfSu2M4hjNuaK8JuMNY+h8/qTwD7qd6KVNERO9IU6ruQqkz/XOkY7KC6EdW8GOFxqrXXSg8Up
4LofZD6Re+wzDAe5ukINz+wLmJrLOGSEtzeC+7Ui5GvQFHjRbJjqa0Fbr7JsmARppcBR32zqVg+NJw3
8vd+1b1dXC7yqTrEb+2tjQyIDV3hVcvejhPVqrXHISM7e2dFCEYx0UR4QCXb8cCUrzhdRUi+8xE7f/l
8JPmzCTl/csm6XCOxSHQn0QUejgmiO0wui5gHDkDCwJva4Ytw3zfFFa/lgEoV58eDQsaGhfgMJ82Y0y
Iq59m0MAMZkFx7hqOPTaUPy/oAhFxOcgo4vC6rzVGNk44WB5qGSFmJoNahMKEjORdP8FdT8QiP28Y3I
YraYsQO5+1vB8fl9pZZCYCCKuzY8K760ubz+AKPocQjVQpS3stwzPop0RkyuR3caRz/C0KmmlSVOJWC
XLaakJ5crI3xW211QkXWV1EBmQWtitPM+oP7QVNzK0ggO0HXzGCyBeJUYiC/bsJDTCvyVaSKwZqaw0Z
Svv1wFNCGBPYoTmE6hGeg0pAZyrPLLhfjLBlZuB+kCjsZlw76s3WBGNrLbA1mZKJhn8543+rZaEJehA
i6S9Pcz1rFgwjXzbTslojainwTe7q9QSQVvprCbpFpgNuAWM1FvezWIOQ5AjsiKBr9+QOpSeiGIoZzY
2aInNO+JGBrdr2+zpsaTdice0vaC/hjCiJopzxm8J5PPzkJHBNBhW+5F+bb188qpkVG0pAzK2R2JUcD
WZthVEGgulfjfDVPdqAvZfruHZ0EBkzy7h1RpfaOjCLwwlVlMfhtvuZHu7MTanq/hZ97UHPrN5gqigi
+shCmYmouPdhxczdvOrNlFaMhG5ACCceq4eR+SrVv2A0/+gf0WJmFT6u/hRFwGeHJYgEQAG2rvd/GRA
i1wk5MNqfoCYXmFShvs4EwTR1ixNuPfX1Pe0kjHRsJ9Vfq4CmvdSAShntUD62b0fQinpqdL2YmeZzTY
LF2zmU7ESGP2NW8/X6vP9jbPdq4+enhb5/v9UZ0VvbLWT8WTRerzbbFhzhHw8esWdkQ0fMaRowxZDVO
4oldJeLfaNOqNMYNa9IaxbZZu0QON2YyoJqp08WIpN6g7KRPRk42q1SI/Dgl0/dxqtvGHfAe0MUywSn
QsUFVopxL5pv4+1jTODfvmLCVKmq+4zysKXvq/gNMNCKozTWO6DB3nJq7rIgDITxh5uss19G3MGG7F4
r0wo5DxbaK3ydC7pDkJQUzTosSt28X4bkUQ24hGAiZrEwEeI0VjFqFEdUTV5bu3XPhzPRYZtLUNV6RK
llkauUShvKRqNmBivMYT1R2G2/p9N9eb9dJGUni53FRkGzmY5tJr4kDCUx0OqujIogCRnJx9ykPklFO
HmTDJNck+lLzcY82EkXmCGXHkpERo/Q5C7WPk92paTIcJtbxoNpWM7zR04WrUjAcMus4/E8Hj7PjI6d
nYTohmwA6CeLSBwoU9smonhs923WsuVXY5XzWjhHT8DxSmL+jwXpZzgfBPD6FvzHZDzByZfCRJgpmxx
JlLPCY8P6Fi6fFCtrFKLqIJv1iaxDkDm5AiWO1gYuEBsX8aOeEj60NPHWHIO9YVk9Ewh6b32nrspg4w
6/GMOT1dZO+mnSZCrNoND9CKW341vpK0tpXXAQ0ufFzQ8OxEby55YBJ3g+o/XAQcbaaCEOBE7ULpmJt
OlUDTOrshHty0SofHj87zUCZiah/t40SmLS+6uyoTuSZKCGt5gLnHH3mV8q0HMVVk6ahGwzaqYBjUiW
aOu0dBLoBpAW7yqxXTPrOcRcTzeihlcRe4b5k2Pdoy0HHiUFw54cG5n2PrJe63zPtGfTYb+/SdByX6e
/c/aFpAiQ/JY749jv2HV7/+W51/e2fmyqGqSas02iCCy75peLwZxHZDTW1y2xMtW7YQAuUHXyhHvv8I
75Y2o87jRLv7doiphatBdP5HLcfQvM+2Gu0X3mWKBJ1COJ/6sXoPkUT8Y1KiW0rBZNUVN6m/Bhg1oda
DRBqcjdUQxOqitj7hgJoFZ11+rYK+WoymGqDxXuLHVVPqrAQ9iCQuG5Zgcldf1at+0EvaJS/FSiJOZg
gYSOLu7z1W0wNWmQ7npiUfv1IdzWpfHx30XzhMxBg0qQA0P/9QGqrOzCY2WYNEtvKxsM5g8l6f/H0I0
xxKN4TQ90US4hQFwx6972aUfGMoCG4GsCoA/u0plKL/ceUEfcIwtj3tGXMtw0wdau2VvWq/1L/YRXZp
uGXyybgVdUZpGP9qvnpfYzubU5Q72/bZgFXrMDG9VVAnbLch3yhr4SGgPXGuwM3wpzKhx3X4T+NjX0+
wXS9bIupO+tiapZ0CiVV5VJ1N/Yi0nuPEQhTlxGL4H1HTZEYT2z4jJ4iqR1Qam5MzOMOR8m+/yqN9W/
UGq2GpVrubeYTPbWPb95N1rWhMHmoGZR1u9FHA20ytNVBN70htz0gMXWq1NgzU+QbPEvjC9B11gmF2Z
dAIe2EQvolUMg7oZB/CRTKTiiUXwKFlScKaLTQvYSvBYGzTjQ4+xI0uPBEQTWO+Q6UmFS15iyLp8Hx8
cWwu24nUvOAJxI22N3rbbBpNAtXSbnWQLOufUekllF+jcl17rDpi+Q70DcpDn423Gb7EHnLW/29Raqs
Doqf3EN1YTzYFa6/g6BnWz61I4uJm6YUTZcdRdSEUKw6imVNtg9miMRsrU5jamphUkUrj4MH7dmtYQc
iu4PLLNgNzfZpV0cbnWp5amtoiUvHXvP5RrXTvJbQV4qtHOUXR8Qp5KZVYss7PqEq0kYDB4AAsk0/Gz
7BVKMF9zXX1pobcpAt1FJKyddRWsAmfmC8mxVoVijQ5LfhU1NMNSPlnea6YXK2okhk9PAsXDENGwuvP
t+LZKzRyhrtDNDn5mq1srNzE9fa4CuWdZUjWML1ftLy3sEEznoFltZ3ATZbmRvHFwG0jiXIoy82fe49
fW9kxLaPRWrnwkZcu4pTUTd6K9hXibPQvC4gdgz3txRr/zvV9P+H1hZSW0d1AR0EurNrvTo1jNl22HZ
saRNx+2imLVqRQYmt1oqI0X0Wlrlf2l2G9aRpogzdbsxhMEYTeTA1q6uuKvoxqv6lNDp651Bn64qROl
JT+C3R3oMgnJVdyYrpC5CWs/+Ol4CaknupEKCD1iU+UcjUn6PVz5ijD8wBqf1GvWqFx9Kga04yH2dpj
3lfgAqZh0EShbS1+tcoz4ruLYSpcyuJ1D5ZVRR31fOkz3csXpBE4zf/cDtL68mYdO/AnPsrVn7dCSsm
tmeT82Rp+oyPOi4CStDN/QAYIiZP8Gk0iRdhEiwptiju5h9HdCoxBWCjvfdhMMXzeX7nLq0OUkx4tw9
QrjfCuE5qXG0U4+HW3Lpbq/GYIDZ7m832EV4b7q+FtaihgbGxWAy4NlS228zTpNflE8ULSpM15A7l16
Ps65Uc0ystrxr+WSQStzGi3fH2dsx2x5iRGfyRvH+8jQtT14FrbWkeyGrivoXIhxdrYv0YPWbzbFVcA
dvW2ULTBAQTG6FEIELXXh81cZNHnY9vefPxrevhY9tI2jK8/h6c31pVzf1jbWbiK+iiIdUl9GvF2cO9
TVZPtQsmTXZB+YVwVGy154nkactu10vWMMJhMp3l1uYVwtN3AixQvhL7iOTHRp2UKExfar3jKrpWzQ4
cB7eDu+0+lXL+FA8Ul6ZOrpQvoFG+nBypWYWoUi3ZXZfQ5zFW4YoFXYULFm21fRTgn7YpWBLSA5Dh4A
HIcGwFvNWmcll359kSbSrZDcr2PsR2ZvcKGHhiQNHPhX7X05WjFiFFqOutX7HgEfi3mUUdewyo4LbNU
ZgUUS45rK0pPXQJOQVn/XavU8e9AVOoPDpdJWEeVCFDgdy41TmxT6OwjGvylRZ1YLtavewbuBOo3VUc
k9hB5Aed+IF1UA8wjb2Ej8RYda5q2s2jpsTTcwtTJ2cswsiHsdVk6gsme60/1nowm5qY/PKkfScfKUx
kNiN29Fif1VNdDydvgjUs/GqqKIR7uwY0hPuTys8LA9NEHYx3BrSNzMfKKNJHI4xWWzq1xeNvS/E6Hy
20aP5t6bN/tfli2McjpYOfkMzGEruyj56NLeRPW+oiODB1YBHPLYN68t7NqKePPlucbQn78EfpxA9Tc
n5zq5OxGpMUfI9osEST5PVIPkxrST//9qptc45OAV80STbt0lZTB+9W+ck6Ax2mDluI9KTYj+umD8vu
HmvLaRK2S0ussXXGE30xdFTos8AGnpXwb2Wqh7/NvKNs8TRzYGLs1u/AbWyQ7ohQd5la212T8Hn0w84
N3ZV0mIRepxTftVhG1t0OZK2+2lvrq42OX2FahziYOvCXSJ3cQ9Wk9lTPcCOm8rar+pUkbb4aevLvqJ
0MciLJmdWXUiA6i4NPHXhpja7dGZ+tteYRXo6jevoKM4mtTjOJdTiK1X/4r8JOQYfm+2iGSGpKwilOH
yi6KzTryMKPX6zLMk36ARqQ11dsDnnYzzwKgDpTFmt2lZaj4C2yFDD1Z5u0/PhFdJjOXHP09TRgYplf
vgrLqOHr2dygY6GYFCF1kBbRBEaPq8koTFdRZTF1GCU7SYM19EbeoidXmBZsPlksy8tgkoRFFS93Ldo
KinY07GD62MneienzjQ+I8W475DTrqqas28cwXUUN9zavSkw7y4/qq1/WUKOvX2fAdNX+iKk7A4m0ho
rPCDhcg4A02q0jCDGtISNEWku5EunLtDomQ2McdtEY1bR++/vLaJHW5piTNTlmY22W+VpNhyJ/3eZbs
wECkv/rNEMnk6P89CqDAqYrmCBF+h1NkSJdh0mypTpf1TQp6/XVTEq/w0jVZXVSpK8x1HOp0WnBUaTf
gYz31xTfNv/Y9XrMlYWQQGki4zdV+6T8XLdcSe3MFE6FOX/QwQ22jgvkrEemvVr/xdS9D3f/4quy3dq
m5PWw7GL95eaoLk3V2S4y6mgMvZK1ocnScA1z4i+1YNaZqL46KIN+2An6t07QnztB3+4E3eZMr6bGkW
7Npl+v2Ts3ZpcR6XpGoiuNQNc78vyOI851WwD9oJB8xmm+TemKy7vdRED1hW9Xrb7o0l0xrWuPvoZl9
nWL76ZqdFQWuolfkdapxjX0//t0Mjb1/gd0KvYV+75cKw/FpnZzufyr93tM69A3yfCUxdsNAZlsqaN3
sZquz65x5UbFtIaWjOnrTd9FA+Hh0niNB99+US7CwyvwRKnsfO3BdvDVpBwmjvBBOsMwFZfdM7gmlnx
AwQ9w99cEA/tfgSnXpQQmTo2uPVqkK/Rska7FaIDpenu6SGv2eJG693yRrtKqmGTLoiigmzVkgUhf2n
bRDVrXlWjX8OfrG6m7erV97uBWLNLaS15fXrv7t1JF6RxhGOgeEMNflQVYyxfzbJVMgzQrcZvYKR0sm
gflPLQe6MiYgA5uIhT+1edq7RDr7oXpukGi88aI9Tz6/QOX1I8OMsJ+VK/b9kze3xi2rb8n1nM4jeya
TwxUU+ct/uIEzd7Qa2H099zlX8f3/saXwVff983NNmLzt3dPNUPkt8UjxfQVgx1oFfOda15lB3/StQl
JsFPzoY6cgGIXr7N3f502NNuvTTh1iV7QXu3iiKIBnDDF5kG3mAVSixkOH1x3xIJaRb5tzqkWjheq8+
3VQvIyufqNx85xPQCmHgOoc/C2jpMcr4NJbYhbZy++0QJ5YnmEVR6zdfPYr/J46h/QDVOHKZOfTtP1N
A9M3iFX1VS2RBsXyU9Uy5hw2I3pKL7akz+tESQPQ2POowsQaEmWr7sKVCmtVw+Rh0nVoAixtshv7dk2
K2Wur7wWpDURweKkMzMMPbjpJRO6smRndvwaQuer9SvF2Hev0zzy2kUJqVB9h/nNcVi8K/FcQiWXX7v
nwunyTTcZK4d7OrYhLePy0pyU+i/QfOVgT5iufJbhejLCFTS/+Ul1x2MjfO7j5kU2DZRnxobTaRKOo6
RfDigikAxfickS9os+POr1WWCjrd6JbaTGjLJZsMwjEG/QvtOjkiuG4yxLojA1OhQfL/o9HhWMZb8b9
IApYIRDz5UBiyWl0EnxnCy58hQWL8/TVy5NSZSyqQPiWdohtE6YJJfBGGM5h4totKmWRQdwP6bqBHQg
GR6xPVnlOca1kuTUnhcTKGBUJ2hcvMvO0z59gu1OEagNsrpQZ4BlFa8ieGiQn5uEzsMioFhB4wgkM9C
ppEe8SUabgTno8C+RGglQY3pZQZs9E2d11CR17q34rsKVOOJejQytNWYv2OcEXO8gCinjxTKJoymiYZ
NHVat7kWXgqphI0yiJSviOlQoI3nP1O5u9lFjCWiv24We9h06zl9QFa6e089PZs/F7kJ1xQsFwM8hSo
j6iQGBQgUFwVhUh3BcyNS9HCDIS1zgBH0enKyXMqUYRTSa6g641BllD3JWvzKbe4K9epsmlrZGV1xjV
5rOrTaiwMR5xrHzhVSNrzDeP8ygl+3HRlkcYonfCQh1utePJsq/DsSaHlyhPGXsUXpWwxqP7CpWohoJ
GNA1tuMoLgwcm0cWIuLsPRSZZtsS9ag6ts0EZZRMdFEl8es1D4LHpDnUcHnvG7UbFNkwgDqaAMEdmVq
IIzq4cn0QliufuRWWH4mEWZFDJDa5QgWElzpVmSCkv1AMcXBPzjMFWXdhWFS5SUP/j/LZpitg6lmdNF
cIqnMmAe7vWMhszEJkQk+7VZIKrKXgdPBfeGrVBkM3IYhRjwoKYi40UBkXbZMoiFGfc8U/IKScr4QLr
GcvErnJSKUyDG7NWZU5A7IR3eVbGmI4HGeMcYqdtAvE8LOejGfSWHD/DPBu97nQah0GxANUMKFxGpw3
eSK0K/BmMhqzqnY4qA/YYnc+h0o1O4AjFGgQFs6U9FXVVbcRFeAEV/k8jfoVGZKTu3DxJlP6neb5O8w
CpW5vnTG0e7I/OhoBMj3hjnjj7ritn2hjsm7VjF3Gjy4QxHLLovTgonnmNB82jvatoGvA8OZmjKA7k0
dG0TY9MNP1IhZU506pg0QNp7kjqr45zWBSrRdQ3pqI4o4K5+88RzI6I0ZdR9EHOr0bBwQzngHOYA4Zp
EOanK5znDPAZAhboRFEGixXMm2ZhDrP7HHML59Ax4NsSJ8s0nSyzYBoXJZBpFRdzcWocqaE0XYvRODA
ajfANhTi2QOwRQH3+h0j0l/rkD2GXKBx2BgEq2PBTKmGR+Wai9yg5jDVIYpss+0B1OHqvzV/dp9Hp3/
nrmvpRptVbbhHj02BsKqTLqzybriYR2VJwSsvDiCO5EYGCiLbMs9M8XCyQMYlPC5104fQsTHEtj2wDS
o3kaS08YrM5HZYHwphTpWqOLTRP+7E5Ys6EkZ3xuJtZliTZOWIr3apdh+OoJ+hQP9MsXyaFrfM93Z/D
jv2QBh3L82FjtZTwmtAEq6KIipapoBVHfWuDHcfbDhxv3/bFcZmsgWJd7LCiq3ljNWPC0x05XnKqpEu
nNEvRqojDUGWgqRkY1bKggqBw1CqMQ3qdVSVirlmuSTB2hqtL3Eu6vU3pAEt12xYaK7GrdBzkql6gTZ
lAXlIZbK7EVgBwVhz8Nvls0T6m7dqHYrejHj9if9kKg2YZax24FK2g+tQ1KW5RzbSyHS1Za4Crzi81W
jTX3jbOLvPojL4QDFt9Ih7LTKtXDquLhFRHkFExj2clO2WycYrv4mK7SBCngdrIawtDblpFtPau2Yhs
uVYW2g4amNG1FbPQlcxAemNy9efNHBSVuKAhFaiflwHMPf52+OzgxZsBPXyVhyWoPGFeRDmMtLQ0FNM
wCj0VHwNfolaEmUE+2IwoV7HFcYU/mwR0LscSconytBihwgVZ4NeUda8IcAk7CUazFXAkaCjQ9+MCs0
viDzDOr6ZBdDGJliXTuGJSrTI06NLYmLGllVmcF1wfwBrAtKUMS3b+O2b1U3iGWGEZIF4+RAXmQ8pbF
BYxusRm3NQf/C08Cw9pzyZUF1kjRPukQBYzSzPId5KEGGJzRFQcIZaYXqxgrgQiICvp0Bp6N+PvnhKK
qQUiiRjEs2hWau+CZLys3o3jlE5WXGbnTN8Mcv76dXw619+z9o0uKVzfB/iFSiKteKsFi6icZ1MYcBN
E4E22DB5n52nwchnluP4IVY4mEaAziQzlE9mhD2VDy8OMFHqArogmgG59Zcd30JELDFWckjCH1gbggF
YPSb2zqT8ViwsNb6uOgrZoaVmPrGQhW0qTK5M2A6ets/as4zOqgm1rm9VJR7Y1zboWYNKcal3pEj28v
lxkK33RRKyvnUX5GJdpnWqHpbxqcRGJR58Bb+tYYMvLbOF931yatagqBJ2auRk5pvUcnbmKnG1SW2rx
VUWadXa1vVBvFyec+p5puQsZ+xhK+NDcrpRgsjC5msQUqj4St9IMk2EESpVjotczAYmFUzGz8h+uMPF
5Kwq7+wp1QDbaWquBMBWvgchztXSN3wCujw+6KrgWGmZCsHam4PrUM6bUlWDmGsBTLtTZ7BmZN8sXSD
+UtuRias6f34cTYAeiyyDIcehRacnpRz9iClRhTODwmv2quppVWDMDe5Pjq+2l0YvJBxsQGlWeYiiYC
YkRTTLQNRsBaLKxJ9+R6tWkkisDle1gapbNgOXto2V/1qidZpTtVyQ2ep4wWrHFfSctPUll5ZdWIuhU
SNvYTq+HY2ByUMqXWm0EkHxUMdpejdEamWmtI86VSd0VuIxmER5kvh6G2+AtlYQXbM281v02GnlKUgt
N5ARPWSDduPOO3vlYXjXBqUzkvzLT/HsxBlu6JMW0P47DwrA4NwsS+3zW1PrRcM1XSW8HVBBZsRun/S
S2yWjSbGc1LUzz8CwiraaqXABzy9/Gn+W4jLeTz57UNfyrYvWZ5Vig9u6IfE1sXTfjkWJi4UTupS86j
6IjNXWgZ7XOQyqLZtnTWcYhnnGkCPu6NK4w8EDKJhUau0R77zdax1CdDK+8Cu26oqBxHa76NkgNb+VA
9Sm0KvzmnBb9gar3qsDWq7tl1fPw1EjQ9mAeNwFdlGl9C0Y/NA4Ul4txlvDlrfM4SXBKE6fzKI+xFuN
LzIuyN9ZV2Kf9YhAY61IX6Gt/CV3t4qg40UaCC2JnNhe/YDIiG78HohlCQuYAuV1YT6mLp7tBYXZZmC
jsBkvzOT8WtajzRMOC1MU9O/9PoyRe9GvCkX9REWVny/FxUS5KBJjZqCZyrpC6UJYTkBCjPCqi/AwaR
1/KviDb014wu+dbj3GSTT404lO9VMuh74zyWwrjeL8IF1H/Qi9rQlWLp7adIHyLmX3LgtjMsK+8+R/T
/OJPRW8mWObRLL5wU05ywp3v1drUyaBSNaXWEx4hM+5/wIuDyj6EZ7tV+X29juU8LkZCP2E2u3rREii
E3o0esr1VGuaXFkdbglKW16jPqs8cy4KKToBLbfjPY5VJCs1VQdPQSqJDkQNRsHtKTgyyUVVfbWuBOH
shWr1xa2EtI2HQI9uR+eKofRWNeXZEeZhORZ062kOEbQe+VPjUu+MhQ3USOMx0FhQmc/qLFk5pZ7kVU
uuIOr/CoSws4swip1X0nB3K6Al4Y/YF4S1SOJcAa+CAln0FiXZQk0P1O7Jv2DbatHLbIWWgmJcbWM6Y
E7kcv2slGAbs62Rq16AZp0LWgroxCM6bJe7SS94mxFhV85Pdz6amnttoYplCy9VSu68G+6pVgbOTS/E
VNEcGEztO3Rmf1lvax2nOJGZVJsJmJSwDzdJSV2sL12vmL8TyiHGbz3i7s9O5nbu3ZoeWRBS1cXnHNt
clzKRpRMiLF+ELrumwPOC9HIMqgGajZcG8qOICYJWBAY/zWixxvZAWL+ClozMromJmK2k2CpfL5LLPB
uwjxZZ00srVtcpu+Hry6KoCK7JnROcwy6sT7wsX2NyZah2JfjVj09UG/rh4lWX5a9FzUhhULENhysYa
jQZ9Anetot2ml5Wb7I5t97CRg7q3RMuATu+wjJ5aFuTn6wHHvHY9AFcpXwz2AcbF/J5rhAqLIj5Ns6U
hoCrBdHdnawS6buFSZ6pBriarBjQ719mUlt11dgpLN7Mh7yuL35WJkK19E8lcajHbr6h8Utv823Rqul
z3fo1mNnTkwAVvyxKb2VFblJLEOT45TyZTBlGVElYXgCa3+cbFfFfIHbvHO9ViZK+HPA5Az9IuRF06Z
U3AjnrM00p55J7DkPbD7PTcIi5v1L5bKcBeRMMJEest5LDT4/zdhWrE6dqQ+ueWlXH4pFEH5jSRExC5
LlZNGt1UYoq63qd6zJXJpaTplNl8nFHsPkYc4b8j88CKghZbRrkYf34nmjm5jCrNzXaVfto6abnh8j2
IU/LGl7xiLKWH6gzhLJuICYmT1JIYDv28acai7NRQ2HfTYN/PJOnlMIE/lcUtLs/jIhIzmeubxvibjV
zTHC5uOYa+i+BdTDZrq0b2OUZn7cjWEtWw/RXG7Oskc8jLaCPzl5nSXH3MaXKX9pDFLpny7ynYBl9bs
jXS4lrEXr23FavZOsZyfyONh9X5yuJLtTbrHCoYvNXCLLqBYleuPbJrYx2syV2k7BUnmIzoYVLRwVgU
Vldjnbti7B58Fh/ecZjqjrs+gSqkfr5rrBY37IfQl4ilNRqlEUcsKr7328Hh4VQZ9MNAlnGe5dOt9Z0
EPwfWdnY7/5rGA3ubim2Htqa/V2t5w01DjJh60eKDumuulLKGXwkzJrjjOgnnGXKOBkmrrLyKTQK1oE
42Q+g1+sS6HUdsjha1NsijcDIPx0nUNx1x5HZPlYSm/809tkEmo6zsLWJrD8cWHlLGcCuqHheYOaRYC
7EVVC+sysBvF4yEbbeDY6pG4wOQHrkkbyHipY+jIIkp6G5Y0pSrzJY4KuAlhVms9gk7tjtj8g7PooxD
soHFDi/uLzLWfXIGgW19xVKkRlXrlluLSwLvGP00Y05SNnZjbwZBPmDBFNEmNCCWUHzg+CbrKbRHybb
00Bx2sSwv1U069Y4v29IMsqgQK40mUVGEOWQULWIM2GltD+k5c083zZrsjtgeFDT+gcZFMfBQ4ZCIPj
QRremkZW1QoJ6x1RCKxjHQSYyNCDBEYyDwS/KQGU0oon9fZ4UqfJ9glh7d67nJMNzcLYtXt3EAe4ZAn
DuBU9BnThGjXu5yEivf/YcC1/cXozIqShmJ4zbR1BtdtkmceDAM3odnITubL1jlSePAanOEMxHU6Ijz
Q1usD617VHnRDnecrDA/LEfX2LB1SHqpOGpaHchyOW/GYSKn2mCZz4AqJN7ZPjp0EKu6k1Z4yTx9rIu
ipPJu5DQ59nTIrNtyskqs0qY0cwqU1g+kblaF3NpbrigNtHo2qk1F0+i8WeXmVjmcKhAwUa8ASRBEsx
nUrG07uWtgbigUA6RKH+CasJMOlS3kGPFgqkp/4zGcfdeBfU0BDNYlczGttejNeshr6P/o5EmrlxXLq
4wqgi0peqUQm8qkRvh9OGYy0LjvmO9FwwxGMXkjMzD4zkLeIJHq82ELTyOU97qbmq3ZxKp/PbZK26Bf
9MfRaZzqQ34IyBydMDtlXcskcBr/amSrvGTZI+cWSMHZmxUVNxUJ2LOzR32ywEsKp7blIRHZw6gXJhZ
xgp/TakY/JeHGsn23CJ0R4GycQf16//Hh/tMnrdEASFfY2VItAS1f9OmTO1tqYfHUGYuvVlD9q9OsOW
Yzm/wYi1u7gWg4VkfEHSQhvznNoOEaMWkSIJjaYhljcnZIQfYGaigk35PGl2ZoSbc9Tu0mdmhnGkwO4
rq4vpkcmKRg4SRo2T+Ke15bILCeLSB9F4SrX3Di2ANeiORkPGiyaRYVNA5TvJBrIJd0R2irazuEddRj
EIIl3IHHfGZ1TGYl8dghsJq6hIvg1883iN/ajOPdLnzzif3lrNJ6Gxh0JsVuq/EAE2fLN6inR5MM1FS
x4o1rtFDrYLEq6Mi1ymqPDDrrxJhLtHOPhMcnrfUWW70TexZLivyFc87Re5gh9DF+aEOFGSirMrVSa2
2vJbYpqA69PpSHse1R+b4NOMAkztm0LT32Ch2Ra0ahpf95bOvmAglbWnF7XWtfNvfoUKbhZAPqtHnOG
l6jcT7hNJ900uXdU4XRclXM+5UZaatlAxymepPY96b0jdWicECBNeOU3g+CLJm+q6YA3EKlmqcU1TUV
+1YUN3aHhQWfdtt3hckx2bc32G/OmQO+Mi03Jnt8VmKOeW67Y3RgGy+FEZ/HqzU5QfDqrM6dNLN8ENj
tEp0Lset4G1Y3U0zqlMMnt5B2McmpjuUbjuqwFVWHzcUsVzbkZ8uhHpJbK9ZtmdZdSzwwxSAH/NVmjO
MLBlathSaGSl8/cX1qnYdiMsPSoGtl4/y96rxjY1KviJDt7WBfLNWUl1KaDPhhD5cBUy6IdDz8on13Y
zz9O5KlZg0wVkstG2NXafmc4of3F7ohQT2doIpHpDw9WngekKKuYItg68bKproJWVtoU0vGQveU2MN6
mRWUtpRg41QlS49lB9DmYUbATtBgYlWX9masRHZWUBWvhcL6IUeKkzjwE23PKa9v2LJeFDaxLDML2D4
5Qhz08KkqMgATGnSjCeNRKM5VGwZ3WNvbhDYfXumVhajA848OD0Wcr5HBk0VBXmPXuDJvt0gJfIzSib
EayxcxSJ0jonHQqxyODcFVbaV3doDGKFFOHCqIq1DjkARQAzUsDvNfpFke4Yl35tr+gMvFQaCtZvjyD
J+B6gOMqdAoU9X8dEy6TP1RaFVpG+I9Nc8yaU2b1s3vBXFwP/j2Hl8fbTLqNJ7dat+kryb7jIaPPC00
UtGwRh+VOzJwhZ9leb/50GCLX0qwzIq4jM8ikYXVucE/6CpHyl4VlWguirWdL9/yPSa7ePlj6wl+sj3
/6HPIL6fXA9pw1pIzJivxoxylWHgarUV3kXxpj8l9OF0r6THVan73e6v7k55sNWcHDVyB50S6prp7dl
/7dMVHbmFqFxhSNNz+ErJBuXvglnuYbE3GvxxH5XkUpZAbNtudLyowmi1CXjZov+5vU63hE6uFREfDL
S58+KfZvGUd0ymjSo8Ug/njsAyPNLZp3p3VQEh3wTZV1qq+8DN1r669KK8VBd2i0zwjbfrfXtVstP7Y
D+uysp+kyDqcYa90A5oKO9zWl3+sA6RNxiBJQQ1dpbG52+fqbpb19sF0LVwHOP8U4V6Vr8B5/3fZ69r
b7ed42iIsXHMc4WCgc5rV1aCcx6m2bsdeLKJpvFpYX8E3kw+Wxb5rEdi/2SipSE+PyePzMD+N07Vo51
yvDFdl1nXG91UrvV+Wfhsc6vZytYqQQ2eHIWMyq/lxukmNyarIoVmtc1jiNSVsW/W62FOU181d+xEuE
j+Li7pE5gsaPs54ROPKdIbOTorx5l+S0PZFIvt5oh79BpOx1t5gTVqlpef+H2f3mLBMvmIP8WJV+0Bu
J6zTO6F1lG3bvlCbPFerGF+Gs0zaNNDHsfjVtWOvyy5m2IH/mxL1P2zaTJ8Wafkfan2JTm0drY3R43A
eLiNzLeLe+rIht0WU7SwX9CWD75qWDITKIDTKLm3fZAe9trbH1PH0qBp5voim9jZPjIafDHCTzhVaH7
42Gl8C8hMr8zA9pTYfWDzSIIO25RkMWYtbiSwRawXOE4bNJllh+c1xz7mnEXMrkhhIPbzDDu+dtPIQ7
gdHZJnwsDulNZn1WUWrku8MAijcbVdFSHRauXg56wN2DxymnXXwJFw7cSb1OMi1cZQWTuu07WvdcVXb
h77iO9OwbFvhdb/Bt6+fNfgNftYZr2DL/Zj39XQ3nLqm6IF8xPqbK+apY9Ov78Qek8MwMiqzZ3hI2aO
wiOyCkZk9sN+aRg9eB5IUnaQay7TaRObI22b7rz76AkK4Zf3CUZtpNAtXSWmvQ0OWWg/yPo9wT9k/bj
zf6AVNG1YsG/YbTmv87NSTnPNUs2INVDDOXzi5J3vGj1k+jfJDPEYIe4iE7KVZGuHYMI+nwPJ4Nc1KY
A26Cos5uyqyJGaPstU4oQ/yeHoaKXthejCiRyW+yVYlXtEbFQU6EqVWONnC4IswOQ8vC7o6y1hBuHmR
FXM6N/N6eRblsyQ7t2dX1aWY5FmS4NVZXMSIuZ4TWrvi8aqM0LpbC78/DicfTnOYfE13lUIwYTtBlhX
AMCzLcDJHR8Fe/QUtDmk7htT38SI8jbRvmKtClmqP82gZhZwUVAmF9nZUAG+FArP4AhrT8RXDEz8oQW
MoMFoq1UUsujk+Y+jjZ5yPmABzQMuK6QS9OyChzVRKQLXMllR54MRsYXIDXKBVPcp7J23U4ETTC+zx5
wNxNbxQri/xOs2aKU4dCjMW3EAPRIPLe3ZyV3V/jtb4npnTkFfWxWsqkFEIf8zL0pitBsKKb6hRvYhd
yQBOQFboriZknOAMgV25MGECQslJuCwYW8kb7MwRbhcpIxv1XPz7nYOF2VfEVs0URxCD3vRQb1l62E5
fJcMm6ipFtNNWKbqJsqz3NNeXYIwKs6dN/MUg2quv5t9Uf7XEdgKopTdRAM+rAR0IaXB3UK2LWPAUJR
8xDlJKtwCjvGomK0AYRMVnOhPhs3YiVrk1kbDKv52AVblN5BMQnCgEpaDHuvhuXZbToKzWYRLSLGOIs
QV6AXbZBjmPlFU+niRRmPNP5uoHQo1hH9a+iJcMI7K+WBAiQtroOMlgjElLY+zIllE6/LjKSipxkmRF
VN3CsFF/Dw9qIPXZtVhsESPnQFllGAj9xMoK3Cw8jNNJHonhXs8c13UEdRpzwQAva+UwWeUFks/4kCo
jVTLQQopiHsbE/1zFx8sIS45/ZSpolNCwv8jODCmTKnCp+lF6rtzQkbURlVHIx/WMCvXjQv1YvS5Bea
dnYWwf/6cxmt5o1+5RLympyLxMejWQYpmElwb70A4PoglGpZ9QOXGKHiHV1VAC8fsyHJuiF8M5DeMyo
q6zCPMPrOqyL6xS4A6qTsiVdroY8h6oZ8dfRkxd5HdZslqk+v0Qtaul/ftZliFDcQjxdB6FU/Npnp3b
M4EXHNbKtRRoiTAtmJI7x4xI8a9rBzBHYNpfu6CYZZauLikFDTFhv9DVVuy3KED5Bb2GVEdy9HRRFrc
RrYrhOMT24QMDljcU/MZuxFhAd+cRk4H1nOjVLFzEyaWdNCrAbm2NWAeiso0aX1wMqSqIh3IpL7g3Bw
VfytnU5WLIL42cJAhd5DIjupSDhLseiOIwnL5fFaU2yWC7LcwPSphKT+ZmtVI8/5cqAGMY7yZhnqO1B
q9BGuXhEDc9RzCLnepVAWlQf42dV7nBrabur+ltdLEM4T2B168xa/mkgRZCIXFVLC7DJJ7QBHycxB9X
DolPmZ2FeRxahgwlO8nQRUM+nEkbshlnyVT8Mlon+IngANaOtgLmlHWLMoG9uk3fSKKyrKt+FXpWDZA
E7lzWrA4tneDqXxSuBuK9vYKopvzKM3XKrzzGpTY79Y38GufgtpLwgzglJYzbbHThqSNiSsc4nzCJBW
MdcV7xcQUzLzbG0ynyyuWQHzA//DXKM2Mow54IYn8REg1Wy6V6y96e5lH0oboNk+U8tOeDNmglHw4pb
uXbObq10sDxISzDD2FqZDeP8/AUng/jPGNZCMhhJp44VaMFeY9JbZk5k6kEZgDVzF8CmTB8ptoAISZ3
DSBsmuIAAOVhmM1mXA1s7FGL8ELpHyoo0UIHlbOGZkhAUGZaQdYBlCmK/j7D/l1e7lZSRXm3KrFTV8Y
a/qCakokHcgwWD0x7Tf1b1o3OotxlLavnbPShysaq2F2lkRV0IFKGFesq6+TajIRZXAfSKisstlbZUa
+abb6XcfPqrmprVXPgj4YXvVaQSxfIMpyiOJD9wxTEHKLWQQy2EEBVD3GC5A3cJWBkH7FAoLaHRuwhB
TDls2p8YIdiJ/dawYQURu4Jx9BWKzZZZDZaskSilGJNj9ojDOwKZWgqWcDH/zWoppDK+9xj6OSaNsxQ
gB+IjcVczTQU43QIpGh8yoYNbnwFUNTM4tmlOXU3voZBIMtDq/VX6uR4TFEuJkLIQOKaTYHmMCE4pVk
/6DfpBztzU2Es3oCjHQkC5qJTmDMoo+Z3zAbNbAAKPxqZk4ERWnbBaBEuSfFiejwNMLgeJ4cpcaPLO+
CztgZapTDnmAI3xdO4roj0cAM6U6vg3RBJleujN4qkeALDrmw3bRoKiAn6VgaYYjVmP0vWwNwSzyrOr
hfxdGrORQlC5tOo29NSTJyQsD6SCzMDdd1Gmn3VGtGp1KTHNerBaXaeh4Tpkqki8DMUNcVr8ZofAG3l
I5KNbQ2E0cs76JUEToWTBYtkBD5jSNOXKvivxMYXatesJj4E9vmeEewQxhi5omU4nJxV64U2H2FapLz
lWLz8xn50mM0t5Z3dzZg7F0AdfI8tsJ0ofkUPQrcfpmvfyu+Mu7ldZi0vzhs1Nyy0vpYw4QzzKeOZIB
RM81W2IzXvjWOOHEqb2dby1/VlxVOmuB9ird7m2STXVPEmR4S4eJedp319GdrM0+U4cBbsGYvYxhalj
r5SIk+1CQzKN3cIkWox4CfZaQrDpMlxrZ4nInX2QOnmZ9XMlWe6ENG9/KhaLJzOmeHjSecY1LJN67cZ
lFx/QhEg649oTbv+CPpxXpq5nylepcJbiQeIqSHHfIdksJhda81VivC4sqRxauBd/RfPbKxztV1QCpg
7LJPb/ytGT78zEUHavaFEy9vE4Qwb/Owo1gPmaNGFRLkI3rCN0HYAgnJsC2/WuDHAESb0CVUZowVbF8
ZO6ZEGJqzJ0mb8IUxCIQke2F0t2bHhVQ+LnTJRFGL3pmJ4Dg1EGyuGaQ2XYgqHhdisuTepuhK9XGk8F
BgUu/peG2eT1LBTXXp+UwHM+1vwf6sTOGIATNMUV0ZpMWOYQoY7aYzQ3N6SavWaoTiyrXCOZsa0htcu
4dbQ+lTDFi8+2zDzCHrL1GMb9tU2SSs6vXlAUZO+tca+Z3cdbjfEGXEXoxaFWbggPHNwRcXC1MQFxmE
sNhHTaZ91Np1a91JHZ5HN87eLW7Na48YIs/40UELCWiZJbKOC/1TJ6AurMXWHppmup7u3cNG1z36lW6
+VKBdkj7Oe4MVeuSVA02jpnKO3BMF9To4HE5yE3rOHdmkIfltXY2hkqNsU6vDuQ30672YR5pgOWmHj5
GqjppC3bjHxYUvnqHFlh/i2kcTmmt5EKHxta3e3uOveXotllpe4iryGLGlUta4lEiwmNRpshW73DYQ+
7eEQHW4BYGzdscnBLuGpPTp1g0pxGCVA62y9sy2pv3FrxrxcJGV46mfEsO0ShI+Z15ne3kCfL2+I8hy
hzSMe2DD8wDo43+4W5ERrEBPAeXjCbkNBpoy2V82qfFRFhBNamDLL4a/Z2pjjrVgTc7yezKPJh0hXcK
r307jAVSs3AHmGud+mzV/P4rwohxNUrltgmFNJGxAuOjSDZDPuW+GCyiarwvl2jis/zrdJ6FEAraS5X
mZpctmaQ55lthOGeIQfdPxyv8bFn9LaIJjW20AmKm/Ypzyz9Tv9xdv2LJI1DBggGeAanynrdhuEnUjX
YA+tVdh58kQjpdNy3tJlEIKY0ROsjeMQ0A2jVmntJlZn2S15rEk1a6e5Ftzt+sluTx7euVM77wkx8WL
cFxGdHgvwHTY2Y2odzmr16krPxg2j1mi0RbSaZt273BUjUDjH7G+axuxvbNToLIAcJ3WbNPjmy9Kggb
ed5LnVRJ5bNvI4sxo1ZWU9+ek6KB1MQKoVFlqP/vWIfdREoaMvx4sN67BHQKWT34dMdkm6p830FFn6v
3uNBxxav/nDGt988v1GunV0/eCXvXWm9SbROkQLwuSOGNRpOmjU63o0pE781DvxlE3OAUw/oyykEzAK
PpB+6flxg63gVYizn9Qwu2J8sCo73wOh7G2OPgJLVo7bN6PJNlebqxvzeztyf3GHrf2L3pr81JbG6Dl
NRrWwzFdJJA5PuVL46jrd683ooDCK3CEiYBL3L4yPajwDBVi9qBzW9UaNz076+9sO2/tvTsnlstM3LL
j1ek10unK0NK/eUzSFAHMa/U3WxHVb0uct9I01ZotNy22z/dhgd/WtSw0Q4Wv8h/5mw66P6Z2i6VxDS
JoGQe5vg7V5alh6jTNCK3aCDmck1oVxvdwLftJ2j4CWebaM8vKy59MV7etL65yY6Dzqj7CXq3fmuzr2
PTcrYlSd1j6Ih0f99Ob5M+X0KHwju+U0+xHP0O6nhu2bUR9N2tQwwu9tloenC8u5gOwbIuI0Pusph4X
bj/DGJKNo4fm0u8Hbgp0DL4oQGRgBtVxEv4aTTcXiA9Ub+lYLhUXNG6uqkIaydZPixuajVY7xO5LLQc
CDi8lzkZGNwzIKoNXO5xn0ImrXaTahk2qLUXAgYQoEug/t8EASsyA6jN4XwQx6YCHPkWuNodnS7lUFN
0Tbu2RgPWiacvrzz3m4pJY/xz08JbQW6EGQkwtJE9E2lnCyVhsVqiv+xTjPzgs6wKXuTQPz3NVCdmh9
9Jtm1ToyKnWDwHCUXA2Ci7oGGTpPJV9h8dz5jQFxt8TgYXA2KrO3uBmDxWILdo2Rn0bJaXG0ala+5JD
1eLVM4gmyXjzdsy3VnbUy0cb2L0f7w/8Jh7+e8N+d4Z9H73aPhye3/rDNYu3ZV6prAQbj6a51rdBAoN
J0W4WQcrK7+/ByclXkERR3BtVh59Jh0vsIdFkfsxvQwZbsqOl5eIaHTTMBtsyjWXzRzUu4wsUx26sox
Nvm5PY79tPcHpZ6oPRW6zGmluoSArJpSVzWBD01G1YlZC1+B/wbuP8C0R4VUZhP5v3phUVhvXAG2bR5
aGA00hCu+HmgKCthPFOOBT0TAUsvtoANmnsmFwJ6xEnlBEseiBvNeDRJ4Q9oAUK5x1mSIaVqVf/4b1r
1OXQ+taZVhDXr5EwQjAXQUT+chmVo/0TGW+0V+aTHYq7Sh9ULFu/WRqyG4KX2DnAdoUtVeWuSDGbG1r
1E/xHF/+aieL2CnA6SBuNYpYjBOcjiZ1XXeOfoGBrC9CUZrnzY3W7DmGZvwlPS3wwzxoDOhucOQEfpS
U2Zg25tOqFTexvqtNBX1V1DkCPMj4H/HnhsyrK/Jvqm9Si9oCumgX3tkH1zO+gFfbnLl0jG8KutU9Yn
QkUJ8lEcemzZ0OA/F9p8k2XBIkwvg/sI+QDJ4DltwYGnHLFIiJZBxyV6LiqmgprfDqguR7Ua4THOI+I
iJA5g33AeqxC0ou2YOBnjLAdPjMLH44YmFUnYIYGjfKdB6j61qs+0zeCJDGxDhKywWeA0a5DLcXC/JV
74NRGlTpjeOJtedjuhN3ZuhOEWKtb4MW9tfmq7WYp1y4rwKzO3m+H02Nw6ZjRVjeews9yhBmwc1RqE8
4K7WR48ftcyxGtWPL7lbZLHS91nozJTsbf1XKWN6oHhHE0BCmqrB7M8W5jdNByhj1BjTcmJKC6CaQTj
Mk5Qp53NGg6aY3tbt//oIwqrfUBe52RYUEYXX1TCEQwQLqFk4NkXbLAIL1FL3AiXyzw7i6ZHlI97X5G
O+ioVX4paFNkqn0T+VpeqAjgfaC2XFkShuVZpGk0whlx+eQ0WHkVpPHdINUx1tZdXuLWx7HXGsCTU2k
VfsH/zeCT6Cg15jp5yf9t7u7vNMZ0klEDGy934GjzLeXnXsgVeEilboX/pPQ+5xOIKOcSSxXrulkpid
cqB0hdvN0L26zUbD/X0u7RanC5X+mAiRky7IOHOtuE0zqwu5uQ6jcEobS/HK6ii/XhOHvnV8qZYjRex
zUvR6T1EYVNtWaG13fpiGRYFxUDp9BUPFGN7xaPh+Y0i4QgDq2Ac1iQqORdms1n7eVZcgNa+ds+oMHn
5Azo9Qer2X+Qdsnyvo8fAcJfUGpxzCKp1+kMWZkh/CqrzIrI/LSw5Y+hX42FszyTN7EWmGcveeJGN3+
MRWPpjDBSvHznrZXxpsIY8joswwZhONBfdDTZh9tOs1mj0r5Yj8bc6HQqjQ5c4pVYREv4KuCJ8m01DH
/Tsyyoolw2XgnBQ+dQVgyCiKcJHGN8HwdkgwIMzOC0oqhI8QRFW4eoS+nyr415tOYWURlRmV4lynJXL
NaTLZtf7lp7cNB5hqsYkqwuDJAoe9vHZBKhp5eZrZrDo4ubIlmzk6Meda6Adyg5OiilN5i0eRgInEZA
lXLoQwiw044dPyeVIODq5Se3yByHGcOEjuObIEnYCU7Uo74PmWc3wZMdHLhYyQc9ER4uq3GCDwjb0Qy
6iNQDam2RhOH6ouY3Ajj6kVsp039hu9LCU3cPQ2BpzJpI9aMwZ07VpampStbYH3r4+mOxmD0yd4jxgM
iii+emMyJ0lR2s8zJn32sm1Fgadtx054kI0HFPVF9bNlqbmHUTuXn1QX49eq1UcQrPjfhN1ZGsOBJOl
cku07h3r8iBrc/l0IHHuyK7dl3qjEu2ks7Klnfaz5kSqVJp6xC1ypwGNJqA4lTTgag4F+uKhSA4n6cB
Ay/65VYfQa803E6s6TLheNdkpTswqtnbluIVKrLfd5T0c5lRtnU80X5Z6y859PASNOTZhVA9cfUunSZ
QXzn7gRhyTZqXkXjLunOQQsdc0RHys9YR42jyYfGQjyCb5xLGbzd5mRxlDjLMuEQTXfXR/fc4JpfZdN
7TWwy3hldQkiPqxAXvVpIas5V22pr3ryTqaf+xIfJqnsCZAxzpuPJQd9Kq86dDmJVyb0MDkQ+Oz5qYy
12PdZimjDv+n+5ePv3HtA48O6dVpGtyIDeT+tbisq9rm3pOl49bMWgJDL0VGRcll0O2mxsv5BHHrmt8
e99b42LIb7UqZiKhgV8qEDhJo17cxNe+dDJgx3blZqkXzEcndxzG1aKyUQRt3YzprDcVnx8OhfEo98S
g8cftI2jyQfSbwlc+LLMdl83CuALKlVfIcK70KbVxVoEo7V3IwOa3097evZFWz2g3W3wXsMdOzm8Nah
dcXNYtdyfQlbUuN4cIVw7CfpU66rSyzpROxtrXha0aK7G6V+4hzEnQNu1ZEsmHLUNhaD/8uhjDdKmKL
6WXtrl+x/280r4+51kYw6esjNEntuvLVJmtarJ6d9p8L1elBY2THa7fTacKp8qkbDhs8NUWy+X0Phx2
tYI1o3F8Ti/vXicSDNZF4sPauBExfqlsxTjJ7li3Qp3Oht8lcu77IaRSXfInR5efJdMrbLqnVvGll7X
iXbHHI5gS4Q+5f9aV8x/5w3dezUQLYqOu5ndc+RtgbzRxlFyGwYRwmAUXOow168GWNxWsbWX9cxcmUw
IrLtAwvAjrIKRhfAldNkhBnNdXbSRlPoImYUSnIZvQGPQZX4WnEt8HiVESJcDwAdezvyroKfy3mS+pr
es+wOOr1FaWvhzp4VXHMYjeoQyiHOI6Xu+r5BRXULjs+Ub5JV9Pdat27r9OWIv/itGIeF4xvTc7HZd9
iki2jo7MT8+3snsGJfNGw4Ls6xEkJNnbBvPEMq1mcRpq5xozXzzMcZ1kShfb8ZmhEwAItQyQ+Fq8Bn+
Jox7LoGU6nSTiOkv4ZaB1AHesubI9C9C6AbPhmzncSxAXuQSKakr7G648PkdkmbC+vxJQznUpiXg6Qg
04TwdwpPZoDo0Z4ENYKj1WF+SurBQtZkUe4fhtQBQstV6oYdzSg3KG13REtef72XQDicxwxsHD7wNMS
ixBQdGQvxze+m6ug4CfcDMwqp+7tcox7zsMJ9JbCNR+tgWTDBMHBLDiHRswj8e40ycYgmahxB5gXPEw
Rhu0HSit2D+hIWRBEWksojM8o2euzTEFGtHj7Ut4UtC6PeCnYDhtt3cZOVqXmLQS1TDezMnoXL5ZJHE
37YnUQyXHABKqgbphAO0wvHV0APxDEHgTjVclW4IqAFJEBoy38ySPOBtSlaMCwE9Uigbx5HudBq4ZIr
I4jYSoA7Auud40dSmsahEQK4OBENV6f3X/n3sY90lZNgWEZ7zuwawtwaOE4hdOgN1LZCo8twg9R9Ryq
mF/ycD8zzCsugSDoiY5twKHhGbSsRZxiIs2scbu8SIrUdBv5FNnAckUHMq/JQK1Xc688j4bDZO3LLdj
JIdvHcUgQSpVi3ku/a4grDd/mgrzahXK7NgK6ERLSqnBIKpFaJVId0C6Z6jCNEkrix4d9ISubzeYKaQ
t1lAseym6PYShcs041NZgcqiq4JXgdjnxhI7tQ+j3xb5LTIl2PvMbku5jQfpgLTS+UuZl6Gn3j9MQI5
5fySDVZ/gUOH+Rzxnu1OV4encK8EydxdjSNGn5GRQfHiiePnu8f8m1eYV5EOct3GiXxok9zXYx2LvfE
iudjdOE0nrKZ8Qi4RDvfiQPgGkPD2w0tv/sbw6H2aDh8YBTK3drcGX9ueqlX4kS732z4GFfi3Tnf03L
abUJjoAF/o93LuG24ryM/g0ZHIWw8pGOJbcUoECCbje+4LtL8KYxaMCZfah+DWO73wvyUBWqyvYS/ie
05LaTbXhykUFRcWkt6Eb6wPUYVw/YcWd76HKpney4nPuJlWBTxaZotcekdDwumW7i6u2MA3FYgYIpuB
xoqQOxUZgvQLQVoge1ihdpWoHDvLQGN0tVUMSDU5YDcoAwCY5WEoDtewCQMMgDAJIYBACaFE5BfY5jc
ZOmMdHjcuxxgWdJ09VlH5I8qulmt4uO4PI+LqIK9qcDCSxCQjeCf6uBZ3gj9Sx36ogX8/n21MebxrOS
nnbs/efBA/4QdjN78jf2jVYr3UY0AMbD+Rb/3sCbKESucR4a1RT68H+EraG78uVd/Q0VgKEkU6/07og
BqOevJIfjVERMrJ/bv5DAS8sI+D4Jvd4TBkKP+6RMd846U/06r1c2bRAZq8u81csGH7OBz1sZ/Ml7/w
l+zRv0v4/1N/p5l/+cd2bnZGhb03z0LUYlKenhAruJHH/G/9rC260TiA7EE6O4RToiZOsJXE5S4eJVl
+WtRBUTZMGhXKymFcI0tMwxjiiEieO91oVJDA3M31Q0nMoxyXwwbyt6h/dR4UVVp9Abf6xkPN/71uGC
DccHG78UFBiq/OycYGF0DN2zYuOG++eiBBcry5QP5TEqg+/exGdVx5I4+KOBgIIHEyGGF0sCUseKOPl
jEqI+wv5Z3eCL8JMpmDEa5M2Bveww6uBajjSzfqkMEsgeNSTdvcji4IH6S63KKhx5vV+OVzksVQ+LRt
Qoz3DPBqkBqAlI+qUMjqu95NDGF4xu3j/4tPAv5dOnt62c4R6XeWM/YOrusj9AViOcoTr/NI3HVECyQ
F2tQPDi69/+396zNbeRGft9fMdbthZRNUbIrzkO2tcnt42pTm93UapOrOq7ONSSH0tgkh+GQknWO8ts
P3XgMHt0ARpZ3c6ngLmtxBsAAjUajX+h21/kIUQt5z7ANvlxXl16bx/BYsaJP/XP9GF5KDjR49+/YEJ
lC+Q5ftvuFHCEOcdO0u3o9G/jDly+3lfVOWyXFu4ux4F5bI6o4/R4d6X7nVdCvegnWh6Bf8c7r124ph
LFqV7FiNmyOjdkY/rZ4tAFD9XBjLMljmbrH/J6E1uoHOWZsH6Vx9J6djZZ1O8ZcZjAfAvE6QustgwOw
v7Owsk5YRfX4A4RwXVOnw9/pYF2KMj0nmVf/iNBjfcSOFYHhUT2nb6xQboXICnrF/brc2h7yMNVpub6
cdP2INefj05qJf44yGBj+hSQGhhR/+o/o6SenKhXfsAvUX977dXUTRfKZBYfnhyM70D1MdgZ4PTN4zR
rXsW7CqXQ2wdHwmm2tbZ6lEhx+58cUIGGugylLa4CRitfNTsaIe9/F5LyPGen3221JJTLU4CD8TfISq
+hxl/CBcNiTi9Swk2r9dIYychJ4sqfd4B9uIlmTwaGSpJoqs/G8XlVr1JO8srGdgwAmavBytcOmOJ6M
n/x49GV1oWJf1obpiGTxsYvV8ZEMXV+PlfSS2UNNcGLiXOoeT6Ipheiu3nt9oHqtfzdSI9i/HWr/3BF
0irz+3XX6xz53Nx4EcaHEL2rQVCLvnokXMP4jjpR/k04ISLd1OJIZ3ZK05OgiCfC3uBtZQ/65vOTHvf
4P5Z/Cvf9jubtiX/7h/LtvU8fPFw2aiOG8F2c9eJGUoIoVO3UPOXcsq9gsGiUhegh9FTe52tebq+s6z
3QP3ki6X3vEYNwDA0BPB+Po+L8od7yHy/fVpWCW7+mKQbXRXEqCmXGaAIoqt2g7fkT82FQgF+yOigkA
IUcFyyApW3FWDP6b9me1i14QstLB752lQW+T9qrZL+dgft3upFoG/L8gxwLCU2ZEzg5Z+vCm2lhoxJk
nS80sWcr9zXNRzo0laqv1cHMmB2s+8F9VvbU+gb55X6BEWSCPqxl7kqfPCWiRy0CGKeqHhxBx/rp5C7
88ipOWDy1qzIoeWsBGZp6Q3JW6YJyhgzKgEOLKtQKHDwqQUlbAqxnhYugBSjn/rJwUI0G4qma/3v0Rg
pdthysGEFn6m5X7cZu8ag2Z0ZRZKb10AhzyJupQjf1GCJ4yYYH9YLmOqBN0v2Osqm1+JVzRWYGgKSl2
oN3KTT1iawH9KckIvuR2hGYrkxfGmtCynmYH73PDngLqEPu3m4f6wmXDfgCjZ+PlklQY0g8ZkjcsK+h
rcL1B7eoUX6tzQpsWFruf1bCL4dmlKclp+rT7Jp1jTxc2Z9Jlk4IU+dQGWswRzooxzF7nZ0l8dB9rdE
KXBwuBq3fV7FwhDrcpsZFkl+rlmLEFRe7yRa7XKQ0UeFqv4nmR7AHphdlWgDmof4OYnsHF81XyhNRjU
DTXcvzuqIPnAd4vrS1/vLMu9NT4wDoyL7fz1ysk+TnAovUd449DHz58hiEh4Yd632FmDyieo1sOUx2t
naUjrEKcsaaCaAat6aCPPIOgSzajoAvHMNBAoMgKadr5lRAfEAtdbmn4QNzSumk3pXujD/P+CvicuIz
/xovsqE96jgNQQRBxj9rXxDgq1dGD8Qo81YYqacwQ/nty9NvXn148nriZ1uDR4WefHrOikduvxHqlBv
AYFHylVACp2B9+M60a6NsOhdmU07nPRKGeIVulCrWNV313MYi2XtolPHikcJothHYSBvD9yr5Q3MCNG
E7cSA/qQ+RIA8w4pSYST2Erch1iK44NFIGCBltxwDSr+5FcBi55nEqOyjDCQWwmG3Vbl/EN02UNFnoi
9wg9Bp4/zD5EshI2Q6EVj9ZK16tVNQ/8FYzCh87gG0Kxk/d15k8ge3D7C/qvIdWkodmwCWal+rPApD4
t7RrlnLbdpDTljhB36wyTh2nksgtFa3Cxv5YyqEq2FM8eovc8BLV/V5h7ClneEjm6R2qQhuH2XxhdZ4
yhDHqz2PXUTnW49sgu7ejPZnJygZZ/8S/pFsONM5h1W+1+qFdVs9/1mp5oJtaz2qJfdmqC+PLga3kxq
HBmW/ypbFvrRDEuCQLV4EIHTOgehAsK4oHah3aGCb01LaWf82jCws+pNgxb/uIX4bO//S2vu8/i6S1k
dH+905P7IEe5RHKJz58rLpHQr2nT/pA17DNM4DVpJbWIaaC0zKRJPtW9DkkuRZ5yhT+LB2mupb3Loba
7Bp9JmisFBUhsWfrXpyPBj1nddPdtZc+5gaPAgF1Z3NqO5hf79bJqYRjVLV7UFqObWifG8lbyS3hrkN
3n3jq4uBRIGNedgtaWKSYZMgWDKpWFKqOidZcbmajKlgc4bz+C+VLKi0qrCrJSOyfVF2JWo6Ki88OEy
eaUjoeE/rAiD6OKO1Si4/ZPFELUpjVCqdHpDLInKszxa3uQ/sujxChD6IKlS/pG5oHY+WULznR9ey3E
pwAtauW+WUV8NzEyiDQ+aPShudNHLWYca8fqPhCbXtWAYILzvIC1mqKZrAB1+g6Fm2Le7IxJPWU+qzg
YhXAiU4w+quRCUiEsLTQk8jlmxAcz+kmdXkwvM5zuOSkDzVlxMQiQOeOsyLSwWDrcLBWKPhAnUU+3qd
YejeEepIx1Zw4geGSPxjKJ+TqSaQB4mSrwiYlKLR+EKO+mEsS9qdu6TUlWOecr1JqpRJG54Y+o6q94A
c9ya91tSynCkQ4CBnVGPKKFgNIfvyA/Ho3+pDtD8hJdeB7c8oZAdLwdrsjIoUagJmheLlBJQTgGHDtv
atU+T5I7Z7Hu5QOZadrvEZ+L21dH8X1FrxNLshy2KjRxI3VRNbr/GKKig2a/Bn+LgMLUJjB9ubSU0Yp
U2XN9VGfywxxjhU1yQqwyEd6sE4f4qj5xMr863jVS00qhLDcAnptVTpnyuZdJS/+Bqog2XIGRmx1qFG
i5addXggvO9X7lneAyDsRu1hTqMkq8Omrr2EgyVHuPTaCxemQHnHhoIsUSAlfKpLSNedDqIGbfZXDhd
sfjz7zRWqRh7SPPYtTFnuu6ljGeXhXS53w820KqkqFNRXQQNnfSYhdBPNsB/H0q1kwwbxBN/UlRrpu1
Ts19MBh5jWSMBtnIPaX8miDiigqHEPMDh+BXQNpbXoruTn3bj/hO02zwXUG8xDnjKE7l/DvQWtMOw9I
p5saOfOeBCQLhSQTFn95+C6iig7WdLoHcLCp2maQMMr6hTy1edEGTpstm9naIHgOH4WK3L4J+l2W7k7
1SHKMz54m1OBbpUWi70OStO1+GHdfqZH1/Fw0BAAUZ2xGgroDQG0HuBA5X1Roz54kN5O6QHhywXpHgU
MYXOayo7uGDmN5eX4spIRMeFSHNu3sYNwQSft2sSP6S781Pyiv9nSqpz0eHnc5f55SdgCHF0JLh+hxt
Cc9QQlGuP6Kz47baocrry/PnxULQyb2Qv/uGIwbFk8tlRUYYEAxiYNqGoXtFX9meo0qknIQS8eosyAZ
AP53jiJ+noUGaaEeDcVke6OvBTgaNM8QX/YIhFl0BnSHz3wsSwE8tbDLLjzpqW6auBBq2RF2NFMMUWF
W8n945OtzdCO0tguT1dCnruUC8xGpmGd/ETictv9ne9MH5Grf3mwzENxdN8fqBd81UANXy+4LD4//Lh
uiBgfKerjZ3I+Ce4hMw2yGVRDqa5+FlwDlUtxMhpi6gZxmgZz5iRm+39aKFyi5c60ztUd8mKL2j5tOx
Zuxyj2yNEf8DxrFPsDeTuofr4xf7zbKega1eugKSGR+oFQu/b77NeKTamm+qxz7ileyP0QPdpzMHKD0
UQFFVwV2u6uneX++3ZfK0Vb3Y3Lj+qauYoSs0O+gu1EVBocMXdn++E7JVXB7wSf+uAaR1YjL6J0EpZS
FqIdSn74YqdN37wSGoNT2ZWsggpveh1MXDsCAmoRVkY95U0m0NA1PjJ1U04eLrXdGsl7fiTdv1qt6dN
xjVugucX5o41hhSV/UE1x6w433HToAvWvXXfSUgbkcfRz3RfIRs4KhQajNHDNXsVrOGSHIg9AkcN0lC
8RnnKPRD0wiGa32LX+mSRbpXbyxrTzLidjgWn/gwN3lspRcj/fQg17DfI0onMni4Fxhcx0mQMnfMlPC
9bFMjHjixEhSxnid2mVYaiFXWcWSJAXeo6o8kaVdQCdcJ7sc3B5DA7JE6sOeRGs8u2LMzepxWXMXU0S
s2tvJVXVdiE7bl9hYoEi5tuaz/14omZXUbW+lwKfRArTsyCpy+l18q4ZminX/R5AUYO4i+LQM9A/1Bo
rLdCvKyvO2R4yqdDT2ckhLwI1ENUIzVu53Q/ifMahGnzST6B3xJLGCJOi7a3Wo3VMkh7BODDDqDRF22
MFq/WPiZeo0tOLL8yYG5z9zRZDgzYGmnVbFZij2BIdrlh8cF3Ku3vOGs4JqClK60F1J3qCoXpF2z0Sl
c3Ejv9ulKQE1bj2gKm7NnHU1pSPMYuYrzwnK3DmoLkd9mTaZy79BwBo0QAFr6bEECisL4095cNcukE2
0movnuAEnMidjs0orp9JKQjGomCb7LWbm0WqiXKqgnmK09Wi+iMGaUBZwpzgIQxkainEysR5JCPvNjd
OUcsESyVuAa57XEB3vbB1zzWkXNxbu3vjaRP4aJ0ZJ+7fS0I8YxadAgbM0hIGS86fszg2aYduDq+CcF
htC5vWTMJzpZkxEqvFkh0FiPAwoOLph7Yvduext3LBqB15fnIxm9VO173okv+FfymNgBtNmKhrmKD87
Zq53w4brcBwuCIFKEFRUfJy2pUKqUV4M7WctPLnUpjUzNbPmk3zfCfzZqmjNaoMugejerNr45E5uTUO
aAH3gd0BiCb0i9FWHyjFw3kk7dOno8h1peePn00AIfCEtEDnQzD5CI1o6jKPdBXizFLHqBHnT3ORD1e
d4Z7i+8K1jhie9V+NeZ6i/Zg5+p1CodpVbJrUCF3kTKsKzm7l0Pk7EBeLUBgWzq/MzGNnc/XIZRE9JI
+EA4hpoSgxlG1H3G303pt3iZR1mKOX3PTpLvM+myIOdetlWbp6nTkTHtDRgEuJE5hyBtSBj9yk07Nxh
eV9spY0aW/eDys5G5mK+ol404Udd7voJEf/a1Qmnu9e5q29w8YFCwaJgtKDYlU3CxJP9pJdZMgyR6pY
fRshHqLMuecOT6yEQ0fjJhTFihwzXbQflZ4KAM5ZI1bcWNfx5aYUouGE5Yk03OrPPWfHzc/UD0/AfFP
w2/nxMFTe6hh8MsFl/uiCV4CIudM6Q7xlkVDe7dvrKSX6N/gXu05YdSZdqp7EopbfsPorWhnjoY4BTT
S4L8TciVuoTrn2Zy/Jrd1mcSLEOhMq3Hc7OnU6ejr17ep6JJ3S85AGv6wx287kRGkYR5WnKBvFxSwa9
WCU2XNeT/vlnLflTmPMYqzk3QHcppZCidfpbzL4AS8RGJ0jRrsmblTgcF8PxybLNluW+rBzb+P4BgCM
UVDtsqKhvSQw180Tn+XjLx82q6v7ystlEbh3aywMq8Rmm5LLr+bDV8RxC2FVgwqAT2UNJ5AeDhkJc33
oE2Qc6rYWcEJS1q2LVYmReKY/pmVYCGrksR3XsbkcyhELy/fzTwKjFC/oFCiDxQ+hiIP5q87UyINCcz
o2d8XqiLH5mXPvJOo6TYDYV2sbG+9y7cqd2rIJ3I3fCQEMoXDb+V8aaJMTqNRdVazLod/eMrhYyVPUR
NMOsWnwnm57SwTPB1btgHaE7hthk4VggR0PE86mMkcEUKj7pHJItoUmK6s0LNjz7hosGx+TTJHyJnYA
wT0DPU686VKqrr1uUDXRqSNwHtSog8WcQySmDa2HEgPbAw2Kfh4c8UB6/yiRtHYRVliePeoaIdCk7w2
/GYCxBkfdrMb2WAHbUc3RENUUY2Jmu8GKjjarCol+BcsF/flGt0nJdOwnXVFnjJBqOhbJtdA9Ng+H7v
fszHprDUTqR9Ul6wYdzyCQeUFPGA4hAQColj7GbkTpEuynsHLq817CB4UMSdeaEk8njzuRuirsX9km6
vG/AIwZGQ7m5mIV4kbcURBGB2P9lNhF2C8lFZJmfGJNuUmM1PBOpXPKg/ghwFtDkcVI6LGm3LTey9rH
13nz3X+9IEu89iy/wQPDN76n10Us9LvJbIK/WYMSb5OuYIYLs/2RMBrA4i40TTz1lYikIkb/x1Np97o
OYSMtQbuj51GaFIzFyvFTOCkE2TN3WLTkeL7VgIpVxyJn/NH3947QbcBPQA5N3t7M83+x2wOdKjP+Or
wRNHuo9cO+sVa6KcXQHrq1HRapOZGVEisjEn/AuX/4XLPykuE9dIMjxBPwxvrG1jEP++O0fZ2fgglvk
oKt2Wt9Wl+FhOGN9jWfXYZEzrwjcK8Wpet+VqWl/u4dIg+nkvy/aqABmr5PPocPsGL8h1LxCCH+B86a
ZzjXm+WGulQH3flZImz3ssVK4PRmJO1kzkUHpNRNZSfjTXTY2O8XCprDjfiyVdLPfNvtU1ZGTJ1ms1E
wjQdpnD9VMIdh48raw0zd3Dd5tmS9R9t6vW87DnekVWb2G8xgvIPF5WYdXbulrOqX6X0hwQvoIwwgux
VMEbwW3CkRQ+39bXGPE+eN7skMCEb/bTZT0LpwWWWHyMy/InQIACUux5Fw3ftM36L0CaEP0MBjjvpXM
pGSel0VFReMJLe/1AoXc3HSUkIZww1IuMxmcX36AmL05hbgVM24mqHzyLBV3PSfNmk315YjOSTfwGcN
8wD1n3fqHEhK3YkLJSFVEDSl1W577qJmXqF01AR9cOIzT0XsS0UhYnwSJlQyivE7fsnTl1N+3fVrd5K
uX7zYBaBisizuvXqPx8/TpvKc53+41YxJ9kzPxwKOBHEl/FQzSk9FJsBAeLxP6MSpN45JUszYnjE3LH
HBaYwps8K3LOiEneGUGHLv2JzogL+4yY/FxnBA0CXf7Jzoh/7n11weyrlIeytGi+9+yZNsfmqS/ducn
mE6K52sMZrdH97tR7KH3r/KeYhdx/aMKiBi/0yX9KwixnbEdMW4jdHhIZCWCI8l7OwBDoRvKDPR61PV
pojarkolxg0K2jAbfjfGToe0PMBJSNgoI0X/vGiBIlA+k+x+1HHQAUxQmwtAow7YWU/4fzb77+9gfru
vGurZYLFRsEbwPjAyfCSjsqGl+dV450kFoostcxDtT35+/iX4QX31SGQk+v0fhLV4KzyFh2FKJCiTwj
gLlZFLgX2NMGrjqfvCggE3WpzN3w6wmTBMgd/qSc1Bc8S5IKsNMwNyGhNDLjAdU11RHfzXTb3AiRks8
E2oxnbYt/Raqg81yqynW1jFep/gr/V7AAa2QSingn6BwUr7JuhDhfxL7TrIvUlLdX9bqJV8Elin7npl
7PBfyjnWB+iVgnkA0iMVh0L06MZA5xA/lOOrQeQ84+4PUEwY/Vm8hMIBcZVccmBkJGXUkScmrKZMtZc
1rWU7qeu52kBxpQF4tyUmKKqfjeikXV9eX42hee7z040/zyhV93Vb4T5LKrq36Lus9PuspdrmLBCg2C
52TSXzdxsP9yIwTDa6TF9lTs+9qqRuCq6hFQr3oGOdVVJ15TRVbDp9zSkUtkBgJJVABc8O+AWq1dOfX
AycxN3Z1gpgTdiOeDgvyIwQXLYCzjQgXHYIe31kGoLyXLNtZQmVDbOubUKdIEP5y1DMR9atVjAl6raN
f3C6Qt3nWQ8IaM4TYEZ4A/7Hwi89bDxf126fMQ7XYWorJMYx48FqzA7G1ATlTgQ/dL8mH7HURe8xvUK
kect09klJ3wqwIGb8srUFy5Iwf+nB6n4kVbxLqun+rdGIJDOUEBBIJsq/D6kDxLXrvd242kc4SO0mXL
84VJIyTWtrqs104Q0bJt9zLUZrdntrfMVfeoBoBMxvSSFOmudqsll/DDCSWB1iSLyCUtl2FKdq0ckCf
KWGdoz7gZlPSnjd1PhUJLgd0bX8DTRYFgWb7DvRjVjFlIF68Ulcejjrm/YyfwmH3zb+ybMfuGu8CjN/
+g3d0uqVuWUBK6wE6O1MqG32GIlkf2GprYGJFLa1B8NSz2B4gPUY/Rn7ZzFNBReKMddpKsrJ9W1gx+X
wBzv4DsRcaPVuxtjHJU/E4Npjj48w9fHf3mIHBF0+VeelU2JElGJlAefjjSDDXVzzlz3uFQF0RR9pKZ
2mbBu6gnO0kU9X2KbXm5itBFKA/k3wjF9nF8Oa+vz7Iui0GhwW1dyxsINv7eajqlKbYZe4xzUgwD2Rk
zOlLgcvQa8u44DVOxhq2UMk+LaryCQI+XFQ03pACFroq/nLBQYaITXTptF7TsfjnNgWCEABshd5PlFI
a+BO7Ercu9ilW5e+EZpuv2dYlqSEd5o3pT7G7nj6+zJQGzv8Q2yBhM5BUDqcS5UET9zvvSrqG+hDop5
L1GhXVoIWP/FnxbAqUSBrVrXzc362Ej2pB3FUq55m/zAVeaQYPiTYjWZSF4qVW5vVU6NqVwm8MbP4yx
MxtV473hnk/F5O7AA2WkhIJ2pLnUVs1cJ0FxRqu4XFVFbFN5hUf9vnaFQDU8Z+F9yMDIOl2f04JUjEO
/miUh+4KXRFBfdxUxHqKab2QtVQ0xUXJFNcBimxmEpdNizW/fU93NZH0R7rUMZMHx6pGYazeBpyMCx1
pi/ScLZRCdUv0p8Qr+IftRuIVSg9ppUjZ0EUVVS32t6039xS9wjcIyyt9doqS4VsHWU7eBwmCx96Q38
6k3UtR/Y32qntW7W/O5N6wSY7GfOE0mb1B5MWGVFeajiMALziVUoe8CEBdjj1pS0yM+MTQUcK1dCFTk
OTNDncXory/YLOlqftcXcnfEjI7Q67WOhixDrSbu6chqsX1nl+getIvcj5ANQ+YNu0g36cKiyoZSORL
uZLv4u9p5l8ndJLMzfQBaSq/iEDWds5tbonm1rHYVidr9mK/Ffqzigltw9TflGNOWFNEUJqKWdKm2Vz
asUqKmb9HlJnsRUqAg6RptvUXyKVE0RUD18Sn/IHuzz1yPG0EyIN+T/uTy2qWsIDa13GPSekjuMRyTU
W/JP8JVS2Qh9dkY6NTl9NQxv63ALdPhXKTY4TNjin2x2B1Hn2TzazOMHioYCM3AvB0Vy1GxQiUtciyN
qtm+INxY5tWurJfDq1FRUsY/FZ9UdAsqnz3kUNjdhjorsi2URuKNlG1e1meQwPAKMhe+PK7PCko8wa7
EiPHfcSvgRcl+gUESa+cZJc2AIRULnA7W1GJ02KqmxxecmsTch9PiswKurwnBYyCQ8InzPb45HW5Tlx
SBtAYgYI2SZYS1cneyzaIK8chlpPQDuX+J2JrksG08KOr5K9k7YMSX8NcpoAPlqWANJccubVXPRAZQj
Vut2AWFwcyiSgHR0QyMsnNIGILpOhnFmgOPzdmfts10Wa1gZwhW4yvQX1fDmboBIzCnKHdS7BU1kqez
bAcbzBJ4oevZ2BaAEQ/TR/2paioF9DFo83a39QJc3jJavzzenL3cFOj7/koD5ixnFkPUyAyr7jD5zYk
ARTVul/UM72X++tewkQbj8Vhsq2R/1aE99kNJfzYBwumSZj5oPNV7hAxGTbC5UEgM9qSbFA63MqfU4O
VMyIhIYp1exNuxThj78hjr/GI9bTcvJD1moRd0olELN2uKt4FiYbn41tfKKCRlmVN5AgA5HL9p6vUQS
CS7NBzIaSrUG+AO79IP3C/3HcRlNy6892e9Yd51Y0O8MMub2XrSseoX1trfY+X+LJk2He2j79LZv8zK
gdoiyjFszsBR67SYlvNxul/+rPPY1Ecdx0V3MN2e6VPKcL9ng8MXHAZul+SGV4zVwZ+//6aFPg9GnQY
BlL3iUQaSK0vNK2OrSYDs8/NzGlidL2unNAJToDj2slbhsmmYZfB6VpqKHGbwP7GqRqY4VmuNiWQIA7
QjGRzO2uiP49umWFc32sFAY3krRI3dtpnvZxXMvD7j2KhQFPXJS65GBjvQDImrmuEnofFVnrO6lWa2F
4aGHMVgvJDioGHMgRlZSCqGnAyCeRjrQVSXoulnhfrLXiTN+g4OaShCUTtGzKi+PHs5VVTn5fFUQB4e
wQVCTfD51p8vm3a/xevU45n8O1JbJ2uC6hOM9HIRqf2libkPvZsI/JEW30EWH6yN+XwiNeVmwKrKy4S
v+w3eeR7hqom/Ms9KWmyGUtr6SrtuOAQUnhjVtt1dyYpuUFA6RczdbCugtErkPzt+rIV/hnkGB6CnJ/
S7+3qpQgGfgDIqzoGS/e04lkYVCsBnKRB93fGuv36W0u6pvbzC/UccDH5B8MEfEQkDyrIgQ67qwkf3W
QK8zBSeFM/iE7ZQZvJWKl2iwIayRhSQRGod4SrTg5VZjbvlLo5yvg7OZ6MYAPkPrhA6ubIDFH+BHx+L
o3RbkQv9IXK8/kspohpFgnUTpc1XaqU3QppCJzv521VVVSas/uDZydOTo5NfHp38amBuDmP3pp2KYoh
WO/QFFn3D389OTn57JP7/6dNPjh9/8nmzud3Wl1c7lKTFu2fFF83+Uhw8xefbZvZWbN+5OEdubm7Gfz
j/RgxtPIOLCN+jc/GXcjyfPD5WTvl1C+EU4Ha9rCDqbsq1tHEWi/1yKacnRjIWLR6rw1158Itejh+r+
eOAleOf8go7lf5gUO0TK1BpqbEKtGIVasXq9Wav4kMjc1lOTpzQCZut+IRgAsGifVqYIaGzhfjXjgTw
1329Gz7VK4X/RYKGX7OU2x1Ve/PkSRF+rJy8uXhyICRju3Mcp+hDSPLzr8S3sZZnlHqElfydo2Ygh35
afA7+IZALrNlUa+kzMjgQaA39iX8OBkFQK2deLpriV+WSDPHjo+K9csLXCzKtdzd1W+mf0i1e/6pXq2
pO+WxCESzdrNyopRwV6Ohufsl0qObnZrlv4X/6QdCZjPdg6js4gw7l+sfNVb2r2G7Q8V9XlZ6rp5ODT
w9AO7ufeh0yfRiI4Pu7wB7ln4KUN0LsRARFltOGPBVZrw8oEmcGsIdt7ZX22Ai0U1FSbTtrPNE6qUrp
pJiDUg5gWHn6uMNx9EvbChM5Do//58f28fDHc/G/9smP508OHx+KB58ej4qDT58eUHkPrEn3cbnR94z
uhuX2co9uO9D7/wFiFQhh
"""

JSLINT_WSH="""
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
"""

COFFEESCRIPT_UTILITIES = """
var __hasProp = Object.prototype.hasOwnProperty;
var __extends = function (child, parent) {
  for (var key in parent) { if (__hasProp.call(parent, key)) child[key] = parent[key]; }
  /** @constructor */
  function ctor() { this.constructor = child; }
  ctor.prototype = parent.prototype;
  child.prototype = new ctor;
  child.__super__ = parent.prototype;
  return child;
};

var __bind = function(fn, me){ return function(){ return fn.apply(me, arguments); }; }

var __indexOf = Array.prototype.indexOf || function(item) {
      for (var i = 0, l = this.length; i < l; i++) {
        if (this[i] === item) return i;
      }
      return -1;
};

var __slice = Array.prototype.slice;
"""

if __name__ == '__main__': 
    main();

