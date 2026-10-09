Cobalt Wrapper v0.2.1

Adds a diagnostic switch. The renderer itself is unchanged from v0.2.0.

The 26.3 run reached the shader path and failed there:

  ERROR: 0:224: '_uniform' : undeclared identifier
  ERROR: 0:224: '_instance_00_00' : Syntax error:  syntax error

Neither identifier exists in desktop GLSL, so the translation produced text that
was never in the source. There was no way to see what, because both the shader
as given and as converted were logged through LOG_D, and LOG_D is compiled out in
a release build -- GLOBAL_DEBUG is 0, so the branch is dead. No log file, no
printf, no android_log. latest.log contained none of it.

v0.2.1 writes both forms to latest.log when CB_LOG_SHADER=1, exposed in the
launcher as an editable renderer setting labelled "Log shader source
(diagnostics)". Off by default.

Deliberately not the existing per-call debug logging: that fires on every
glClear and every glBindTexture, which is hundreds of megabytes and enough
startup delay to look like a hang. Only the two shader dumps are gated.

If you turn it on and Minecraft fails the same way again, latest.log in the
plugin's nativeLibraryDir/cobalt will contain the exact GLSL that went in and the
exact ESSL that came out, which is what the next fix has to be written against.
