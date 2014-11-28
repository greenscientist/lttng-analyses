#!/usr/bin/env python3
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

import argparse
import sys

try:
    from babeltrace import TraceCollection
except ImportError:
    # quick fix for debian-based distros
    sys.path.append("/usr/local/lib/python%d.%d/site-packages" %
                    (sys.version_info.major, sys.version_info.minor))
    from babeltrace import TraceCollection
from LTTngAnalyzes.common import ns_to_hour_nsec
from LTTngAnalyzes.sched import Sched
from LTTngAnalyzes.syscalls import Syscalls
from LTTngAnalyzes.block import Block
from LTTngAnalyzes.net import Net
from LTTngAnalyzes.statedump import Statedump


class ProcInfo():
    def __init__(self, traces):
        self.trace_start_ts = 0
        self.trace_end_ts = 0
        self.traces = traces
        self.cpus = {}
        self.tids = {}
        self.disks = {}
        self.ifaces = {}
        self.syscalls = {}

    def run(self, args):
        """Process the trace"""
        self.current_sec = 0
        self.start_ns = 0
        self.end_ns = 0

        sched = Sched(self.cpus, self.tids)
        syscall = Syscalls(self.cpus, self.tids, self.syscalls)
        block = Block(self.cpus, self.disks, self.tids)
        net = Net(self.ifaces, self.cpus, self.tids)
        statedump = Statedump(self.tids, self.disks)

        for event in self.traces.events:
            if self.start_ns == 0:
                self.start_ns = event.timestamp
            if self.trace_start_ts == 0:
                self.trace_start_ts = event.timestamp
            self.end_ns = event.timestamp
            self.trace_end_ts = event.timestamp
            payload = ""
            override_tid = 0

            if event.name == "sched_switch":
                sched.switch(event)
            elif event.name[0:4] == "sys_":
                payload = syscall.entry(event)
            elif event.name == "exit_syscall":
                payload = syscall.exit(event, 1)
            elif event.name == "block_complete" or \
                    event.name == "block_rq_complete":
                block.complete(event)
            elif event.name == "block_queue":
                block.queue(event)
            elif event.name == "netif_receive_skb":
                net.recv(event)
            elif event.name == "net_dev_xmit":
                net.send(event)
            elif event.name == "sched_process_fork":
                sched.process_fork(event)
                if int(event["child_tid"]) == int(args.pid):
                    override_tid = 1
                    payload = "%s created by : %d" % (
                        ns_to_hour_nsec(event.timestamp),
                        event["parent_tid"])
                else:
                    payload = "%s fork child_tid : %d" % (
                        ns_to_hour_nsec(event.timestamp),
                        event["child_tid"])
            elif event.name == "sched_process_exec":
                payload = "%s exec %s" % (
                    ns_to_hour_nsec(event.timestamp),
                    event["filename"])
            elif event.name == "lttng_statedump_process_state":
                statedump.process_state(event)
                if event["pid"] == int(args.pid):
                    override_tid = 1
                    payload = "%s existed at statedump" % \
                        ns_to_hour_nsec(event.timestamp)
            elif event.name == "lttng_statedump_file_descriptor":
                statedump.file_descriptor(event)
                if event["pid"] == int(args.pid):
                    override_tid = 1
                    payload = "%s statedump file : %s, fd : %d" % (
                        ns_to_hour_nsec(event.timestamp),
                        event["filename"], event["fd"])
            elif event.name == "lttng_statedump_block_device":
                statedump.block_device(event)

            cpu_id = event["cpu_id"]
            if cpu_id not in self.cpus.keys():
                continue
            c = self.cpus[cpu_id]
            if c.current_tid not in self.tids.keys():
                continue
            pid = self.tids[c.current_tid].pid
            if int(args.pid) != pid and override_tid == 0:
                continue
            if payload:
                print("%s" % (payload))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='I/O usage analysis')
    parser.add_argument('path', metavar="<path/to/trace>", help='Trace path')
    parser.add_argument('pid', help='PID')
    args = parser.parse_args()
    args.proc_list = []

    traces = TraceCollection()
    handle = traces.add_trace(args.path, "ctf")
    if handle is None:
        sys.exit(1)

    c = ProcInfo(traces)

    c.run(args)

    traces.remove_trace(handle)
