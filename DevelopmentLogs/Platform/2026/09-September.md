# Platform - September 2026

## September 12 — NinjaTrader recovered: compiling again after a month on a stale assembly

The laptop running the strategy fleet had not successfully compiled since August 10. A shared C# library was deployed into bin\Custom, where NinjaTrader compiles every .cs file it finds at startup, and the platform stopped opening at all. The uninstaller failed too, so the fix was a full reinstall.

The repair had in fact been made days earlier and was sitting in the cloud copy. It never arrived, because OneDrive was not running on that machine. Two views of the same synced folder had diverged by a month with no error surfaced anywhere, which is why every symptom pointed at code and none of it was.

Three fixes landed. The offending files were quarantined outside the tree and the compile went green in 25 seconds, advancing an assembly that had been frozen since August and was missing sixteen strategy files. The NinjaTrader data folder was moved out of OneDrive entirely, since a trading platform writing a live SQLite database into a sync folder is how the install was corrupted in the first place. And the automation that drives compiles was repaired twice: it had been calling Invoke on a submenu parent that only supports Expand, and its data directory was hardcoded to the old path, so a deploy would have written to the abandoned tree and then reported success by reading the old assembly.

That last one is the pattern worth keeping. Four separate things reported success while doing nothing: the compile tooling, the log writer, the posting scheduler, and the status check. Exit code zero is not evidence.
