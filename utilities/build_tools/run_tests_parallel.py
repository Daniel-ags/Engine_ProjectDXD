"""
Runs the test suite across several processes.

    python utilities/build_tools/run_tests_parallel.py              # everything
    python utilities/build_tools/run_tests_parallel.py city turn    # only modules whose name contains "city" or "turn"
    python utilities/build_tools/run_tests_parallel.py -j 4         # on four processes
    python utilities/build_tools/run_tests_parallel.py --slow       # with the slow tests too

Each test module runs whole, in one process, so its tests keep the order and the
shared state they have in a serial run. Modules are handed out one at a time to
whichever process is free. Output is shown only for modules that fail.
"""
import argparse
import contextlib
import io
import multiprocessing
import os
import sys
import time
import traceback
import unittest
from multiprocessing.connection import Connection, wait
from pathlib import Path
from typing import List, NamedTuple, Optional

# This file is utilities/build_tools/run_tests_parallel.py, two directories below the repo
REPO_ROOT = str(Path(__file__).resolve().parents[2])
TEST_DIR = os.path.join('app', 'tests')


class ModuleResult(NamedTuple):
    module: str
    tests_run: int
    skipped: int
    passed: bool
    seconds: float
    output: str  # what the module printed, and its failure report


def find_test_modules() -> List[str]:
    """Every module `unittest discover -s app/tests -p 'test*.py'` would run: the
    test*.py files of app/tests and of the packages under it."""
    modules = []
    for directory, subdirectories, files in os.walk(TEST_DIR):
        # A directory without an __init__.py is not a package, so discovery stops there
        subdirectories[:] = [sub for sub in subdirectories
                             if os.path.exists(os.path.join(directory, sub, '__init__.py'))]
        for file in files:
            if file.startswith('test') and file.endswith('.py'):
                path = os.path.join(directory, file[:-len('.py')])
                modules.append(path.replace(os.sep, '.'))
    return sorted(modules)


def prepare_worker():
    """Runs once in each process, before it is handed its first module"""
    # In a serial run, discovery imports every test module before any test runs,
    # so the engine harness has imported the state modules while the sprites are
    # loaded. Here a process imports its modules one at a time, and one that
    # imports a state module without loading the sprites first leaves None in its
    # class attributes (menus.Trade.trade_name_surf) for the modules after it
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import app.tests.engine_harness  # noqa: F401


def run_module(module: str) -> ModuleResult:
    """Runs one test module in this process"""
    output = io.StringIO()
    start = time.perf_counter()
    # Engine modules print as they are imported, and tests log warnings on purpose.
    # With several processes sharing one terminal that would all arrive interleaved
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        try:
            suite = unittest.defaultTestLoader.loadTestsFromName(module)
            result = unittest.TextTestRunner(stream=output, verbosity=1).run(suite)
        except Exception:
            # The module could not even be imported. Left to escape, this would end
            # the whole run without saying which module it was
            traceback.print_exc(file=output)
            return ModuleResult(module, 0, 0, False, time.perf_counter() - start, output.getvalue())
    return ModuleResult(module, result.testsRun, len(result.skipped), result.wasSuccessful(),
                        time.perf_counter() - start, output.getvalue())


def worker_loop(connection: Connection):
    """A worker process: runs each module it is sent, until it is sent None"""
    prepare_worker()
    while True:
        module = connection.recv()
        if module is None:
            return
        connection.send(run_module(module))


class Worker():
    """A process running one module at a time. A multiprocessing.Pool waits
    forever on a module whose process died (a segfault in pygame); one process
    per pipe says which module it was"""
    def __init__(self):
        self.connection, child_connection = multiprocessing.Pipe()
        self.process = multiprocessing.Process(target=worker_loop, args=(child_connection,), daemon=True)
        self.process.start()
        # Only the child holds its end now, so the pipe ends when the child does
        child_connection.close()
        self.module: Optional[str] = None

    def give(self, module: str):
        self.module = module
        self.connection.send(module)


def run_modules(modules: List[str], jobs: int) -> List[ModuleResult]:
    """Runs the modules on `jobs` processes, each handed a module once it is free"""
    results: List[ModuleResult] = []
    waiting = list(reversed(modules))  # popped from the end, so in order
    workers = [Worker() for _ in range(jobs)]
    while True:
        for worker in workers:
            if worker.module is None and waiting:
                worker.give(waiting.pop())
        busy = [worker for worker in workers if worker.module is not None]
        if not busy:
            break
        ready = wait([worker.connection for worker in busy] + [worker.process.sentinel for worker in busy])
        for worker in busy:
            if worker.connection not in ready and worker.process.sentinel not in ready:
                continue
            try:
                result = worker.connection.recv()
            except (EOFError, OSError):
                worker.process.join()
                result = ModuleResult(
                    worker.module, 0, 0, False, 0.0,
                    "The test process running this module died (exit code %s). What it printed "
                    "as it died, if anything, is above, where it named the test it was running\n"
                    % worker.process.exitcode)
            worker.module = None
            results.append(result)
            sys.stdout.write('.' if result.passed else 'F')
            sys.stdout.flush()
            if not worker.process.is_alive():
                workers[workers.index(worker)] = Worker()
    for worker in workers:
        worker.connection.send(None)
    for worker in workers:
        worker.process.join()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the test suite across several processes.")
    parser.add_argument('filters', nargs='*',
                        help="run only the modules whose name contains one of these")
    parser.add_argument('-j', '--jobs', type=int, default=min(8, os.cpu_count() or 1),
                        help="number of processes (default: %(default)s)")
    parser.add_argument('--slowest', type=int, default=0, metavar='N',
                        help="also list the N slowest modules")
    parser.add_argument('--slow', action='store_true',
                        help="also run the tests skipped unless LT_SLOW_TESTS is set")
    args = parser.parse_args()
    if args.slow:
        # The worker processes inherit it
        os.environ['LT_SLOW_TESTS'] = '1'

    modules = find_test_modules()
    if args.filters:
        modules = [module for module in modules if any(text in module for text in args.filters)]
    if not modules:
        print("No test modules match %s" % args.filters)
        return 1
    jobs = max(1, min(args.jobs, len(modules)))

    # What the engine and editor do on startup. Some tests regenerate these source
    # files as well; done here first, theirs changes nothing, so no process can
    # import a file another is halfway through writing.
    # Imported here because every worker process imports this file, and none of
    # them generates anything
    from app.engine.codegen import source_generator
    with contextlib.redirect_stdout(io.StringIO()):
        source_generator.generate_all()

    start = time.perf_counter()
    results = run_modules(modules, jobs)
    seconds = time.perf_counter() - start
    print()

    failed = [result for result in results if not result.passed]
    for result in sorted(failed, key=lambda result: result.module):
        print('=' * 70)
        print(result.module)
        print('=' * 70)
        print(result.output)

    if args.slowest:
        print("Slowest modules:")
        for result in sorted(results, key=lambda result: -result.seconds)[:args.slowest]:
            print("  %5.1fs  %s" % (result.seconds, result.module))

    tests_run = sum(result.tests_run for result in results)
    skipped = sum(result.skipped for result in results)
    print("Ran %d tests from %d modules in %.1fs on %d processes"
          % (tests_run, len(results), seconds, jobs))
    if failed:
        print("FAILED (modules=%d): %s" % (len(failed), ', '.join(result.module for result in failed)))
        return 1
    print("OK (skipped=%d)" % skipped if skipped else "OK")
    return 0


if __name__ == '__main__':
    # Tests open the sample projects by relative path, and import `app`
    os.chdir(REPO_ROOT)
    sys.path.insert(0, REPO_ROOT)
    sys.exit(main())
