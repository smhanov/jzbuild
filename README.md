I love languages where you need years of experience to write code that works,
and languages where if you don't do everything exactly right, you will shoot
yourself in the foot. (See my article [C++: A language for
next generation web apps](http://stevehanov.ca/blog/?id=95). Naturally, I love
javascript.

Fortunately, Javascript has tools that will help catch bugs before you run it.
One is JsLint. Following Douglas Crockford's crazy rules eliminates many
cross-browser compatablility problems, and it syntax-checks the code too. The
Google Closure compiler performs static analysis of the code to catch a few
more problems, and as a bonus it will compress and obfuscate your code for you.

JZBUILD is a build system to simplify the process.

[Download JZBUILD](http://github.com/smhanov/jzbuild/raw/master/jzbuild.py)

Like any of the other dozen javascript build systems, JZBUILD will:

* Run all of your javascript through a built-in copy of jslint for error
checking.
* Concatenate files together and feed them into the Closure compiler or YUI
compressor, without sending your code over the web.
* Process include directives. JZBUILD resolves dependencies so your files
will be included in the proper order.
* Include files from other folders. For example, you might have a folder full
of re-usable javascript components that are used in several projects. JZBUILD
will let you pull these files into your current project.

JZBUILD is designed to be easy to use.

* JZBUILD only requires python and Java to run. If you don't have another
tool that it needs, it will download it automatically.
* You don't need any configuration file. By default, JZBUILD will process all
files in the current folder.
* JZBUILD includes built-in "externs" for the closure compiler, so it will
work with projects that use the jquery javascript library. It includes other tricks to make the compiler work on your code.
* It works on Linux and Windows

## Tutorial

Although this example is in Windows, JZBUILD works equally well on Linux.

Suppose you have a folder full of javascript files -- eg, foo.js, and bar.js.

<pre>
 Directory of H:\demo

07/29/2010  09:25    &lt;DIR>          .
07/29/2010  09:25    &lt;DIR>          ..
07/29/2010  09:26              8392 foo.js
07/29/2010  09:26              2303 bar.js
               2 File(s)           10293 bytes
               2 Dir(s)     377,483,264 bytes free
</pre>


Run JsLint on them:

<pre>
jzbuild.py
</pre>

Run JsLint and concatenate them together into MyWebApplication.js:

<pre>
jzbuild.py --out MyWebApplication.js
</pre>

Run JsLint and compress them using the YUI compressor into MyWebApplication.js. The YUI compressor will be downloaded for you. 

<pre>
jzbuild.py --out MyWebApplication.js --compiler yui
</pre>

Run JsLint and compress them using the Google closure compiler into
MyWebApplication.js. The compiler will be downloaded for you. 

<pre>
jzbuild.py --out MyWebApplication.js --compiler closure
</pre>

### Included files

JZBUILD processes include directives by searching the current folder and any
included files. Suppose foo.bar contained a line like this:

<pre>
//#include &lt;bar.js>
</pre>

And bar.js contained a line like this:

<pre>
//#include &lt;MyUsefulFunctions.js>
</pre>

Where MyUsefulFunctions.js is in the folder <tt>../shared</tt>. Then you can
compile your whole web application by specifying only "foo.js" on the command
line:

<pre>
jzbuild.py --out MyWebApplication.js --compiler closure -I../shared foo.js
</pre>

The -I option says to search the given path for input or included files.
JZBUILD takes a list of input files on the command line. It reads each of them
and processes included files as well, and sticks all of them together before
sending them to the output file.

Note: It is incorrect to say JZBUILD "includes" files. The files are only included once, no matter how many times you specify "#include". This directive will be renamed "@require" in a future version.

## Advanced Usage

When it starts, and you didn't specify "--out" on the command line, JZBUILD
will look for a file named "makefile.jz" in the current folder.

## Example makefile.jz

Here's an example makefile.jz. In it, we specify two projects to build. The
"release" project will use the closure compiler to create MyWebApplication.js
from "foo.js" and all files that it includes, searching in the folder
"../shared" for any included files. It will also prepend "license.js" to the
output.

It also specifies a second project, called "debug". The "debug" project
contains the option "base: release", which means to inherit all the settings
from the "release" project.

When this makefile is in the current folder, you can build a specific project
by specifying its name on the command line. For example, to build the release
project, use:

<pre>
jzbuild.py release
</pre>

<pre>
// You can use comments in a JZBUILD makefile.jz. The file format is exactly like
// JSON, except that quotes and commas are optional.
// A file is an object of projects. Each project produces one output file.
// When you invoke JZBUILD you must specify a project to build unless there
// is only one in the file.
{
    // Here is a project description. You only need one project but we will
    // define several for completeness.

    // You can give a project a name. You can use it to refer to the project
    // from other projects.
    release: {
        // The output file will be created from the input files. It is a
        // string with the path to the output file.
        output: MyWebApplication.js

        // 'input' is an array of input files. You should use only the filename
        // and not the path. When jsbuild starts it will automatically find
        // the files it needs from the include path. It will also expand this
        // list based on any //#include <filename.js> directives.
        input: [foo.js]

        prepend: [license.js]

        // The include path specifies an array of paths to search for files.
        // It always includes the current folder.
        include: [../shared]

        // The compiler specifies the compiler to use. The default compiler is
        // 'cat' which simply appends files together. The other
        // option is 'closure' which refers to Google's closure compiler. If
        // you do not have the closure compiler JZBUILD will download it for
        // you. However you will need to have Java installed to use it.
        compiler: closure

        // Here are the options to the closure compiler.
        compilerOptions: [
            --compilation_level ADVANCED_OPTIMIZATIONS
            --warning_level VERBOSE
        ]
    }

    // Here is a second project.
    debug: {

        // This project is special because it inherits all the properties from
        // its parent project. It specifies the parent by name.
        base: release

        // Here we override the options to the closure compiler to include
        // pretty-printing so we can easily see what it is doing.
        compilerOptions: [
            --compilation_level ADVANCED_OPTIMIZATIONS
            --warning_level VERBOSE
            --define=ENABLE_DEBUG=true
            --formatting PRETTY_PRINT
        ]
    }
}
</pre>

## Goodies to make the Closure compiler work properly

### Built in externs

An externs file is built in to JZBUILD, so you can use the jquery library with the closure compiler, and it will give you useful warnings when you call the functions with the wrong parameter types. 

### @export annotation
A painful reality (and the whole point) of using the advanced compilation mode of the closure compiler is that it renames everything, so if you need to refer to a property of an object from HTML then it won't work unless you "export" it <a href="http://code.google.com/closure/compiler/docs/api-tutorial3.html#export">as described here.</a>

JZBUILD makes this easy using the @export annotation. For example:

<pre>
//@export MyGreatObject
/** @constructor */
function MyGreatObject()
{

}

//@export MyGreatObject.prototype.dostuff
MyGreatObject.prototype.dostuff = function()
{

}
</pre>

When the compiler is set to "closure", the above will cause JZBUILD to add the required exports to the code. Specifically:

<pre>
window["MyGreatObject"] = MyGreatObject;
MyGreatObject.prototype["dostuff"] = MyGreatObject.prototype.dostuff;
</pre>

## License
The JZBUILD system is open source. It is released to the public domain. However, it contains portions of code that fall under other licenses. The full license information is found in the source code.





