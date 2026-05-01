#!/usr/bin/env python3
"""Concurrent API lock test for ParrotPi server.

This script launches several worker threads that fire REST calls at the server
at nearly the same time. It exercises:
- POST /say
- POST /servo/beak/open
- POST /servo/beak/close

The goal is to verify the server enforces a single active play/beak session.
"""

import argparse
import json
import random
import threading
import time
import sys

try:
    import requests
except ImportError:
    print("ERROR: requests is required. Install with: python -m pip install requests", file=sys.stderr)
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(description="ParrotPi concurrent API lock tester")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000",
                        help="Base URL of the ParrotPi server (default: http://127.0.0.1:5000)")
    parser.add_argument("--clients", type=int, default=6,
                        help="Number of simultaneous client threads per round")
    parser.add_argument("--rounds", type=int, default=10,
                        help="Number of concurrency rounds to execute")
    parser.add_argument("--delay", type=float, default=0.1,
                        help="Delay between rounds in seconds")
    parser.add_argument("--verbose", action="store_true",
                        help="Print detailed request/response logs")
    return parser.parse_args()


ACTIONS = [
    {"name": "say", "method": "POST", "path": "/say", "body": {"phrase": "Squawk3"}},
    {"name": "say", "method": "POST", "path": "/say", "body": {"phrase": "Does He Talk"}},
    {"name": "beak_open", "method": "POST", "path": "/servo/beak/open", "body": {}},
    {"name": "beak_close", "method": "POST", "path": "/servo/beak/close", "body": {}},
]


class ResultCounter:
    def __init__(self):
        self.lock = threading.Lock()
        self.total = 0
        self.success = 0
        self.busy = 0
        self.errors = 0
        self.responses = []

    def add(self, status, payload, action_name):
        with self.lock:
            self.total += 1
            if status == 200:
                self.success += 1
            elif status == 423:
                self.busy += 1
            else:
                self.errors += 1
            self.responses.append((action_name, status, payload))


def worker(base_url, action, barrier, results, verbose):
    try:
        barrier.wait()
    except threading.BrokenBarrierError:
        return

    action_name = action["name"]
    url = base_url.rstrip("/") + action["path"]
    body = action["body"]
    headers = {"Content-Type": "application/json"}

    if verbose:
        print(f"[START] {action_name} -> {url} {body}")

    try:
        if action["method"] == "POST":
            response = requests.post(url, json=body, headers=headers, timeout=10)
        else:
            response = requests.get(url, timeout=10)

        payload = None
        try:
            payload = response.json()
        except Exception:
            payload = response.text

        results.add(response.status_code, payload, action_name)

        if verbose:
            print(f"[RESULT] {action_name} {response.status_code} {payload}")

    except Exception as exc:
        if verbose:
            print(f"[ERROR] {action_name} exception: {exc}")
        results.add(-1, str(exc), action_name)


def run_round(base_url, clients, results, verbose):
    barrier = threading.Barrier(clients + 1)
    threads = []

    for i in range(clients):
        action = random.choice(ACTIONS)
        thread = threading.Thread(target=worker, args=(base_url, action, barrier, results, verbose), daemon=True)
        thread.start()
        threads.append((thread, action))

    if verbose:
        print(f"Launching {clients} clients in this round")

    barrier.wait()

    for thread, action in threads:
        thread.join(timeout=15)
        if thread.is_alive():
            print(f"WARN: {action['name']} thread did not finish in time")


def print_summary(results, duration):
    print("\n=== SUMMARY ===")
    print(f"Total requests:   {results.total}")
    print(f"Successful (200): {results.success}")
    print(f"Busy responses:   {results.busy}")
    print(f"Other errors:     {results.errors}")
    print(f"Duration:         {duration:.2f}s")
    if results.total:
        busy_pct = results.busy / results.total * 100
        print(f"Busy response rate: {busy_pct:.1f}%")

    if results.errors > 0 and results.responses:
        print("\nSample error responses:")
        for action_name, status, payload in results.responses:
            if status not in (200, 423):
                print(f"  {action_name} -> {status} -> {payload}")
                break


def main():
    args = parse_args()
    print("ParrotPi API lock test")
    print(f"Base URL: {args.base_url}")
    print(f"Clients: {args.clients}, Rounds: {args.rounds}")

    results = ResultCounter()
    start_time = time.time()

    for round_number in range(1, args.rounds + 1):
        print(f"\n=== Round {round_number}/{args.rounds} ===")
        run_round(args.base_url, args.clients, results, args.verbose)
        time.sleep(args.delay)

    duration = time.time() - start_time
    print_summary(results, duration)


if __name__ == "__main__":
    main()
