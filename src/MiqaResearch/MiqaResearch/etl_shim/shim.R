# The ETL sandbox R shim (#166), R side -- see r_shim.py for how the two halves fit together.
#
# Usage: Rscript --vanilla shim.R <sandbox root> <rows file>
#
# A Script author's script.R defines `main <- function(ctx) { ... }` and calls `emit(row)` once per
# output row, where `row` is a named list (or a one-row data.frame) of the Datatype's fields. `ctx`
# is a list: `input_dir` (path to the staged input), `datatype` and `config` (from manifest.json).
# Rows are only written here as raw JSON lines; r_shim.py validates them and writes result.jsonl.
#
# Exit codes (the child protocol r_shim.py maps onto contract.py): 0 main() returned, 1 the
# script's own code raised, 2 script.R doesn't parse or defines no `main` function.

suppressPackageStartupMessages(library(jsonlite))

EXIT_SUCCESS <- 0L
EXIT_SCRIPT_ERROR <- 1L
EXIT_CONTRACT_VIOLATION <- 2L

args <- commandArgs(trailingOnly = TRUE)
root <- args[[1]]
rows_path <- args[[2]]

manifest <- fromJSON(file.path(root, "manifest.json"), simplifyVector = FALSE)
ctx <- list(
  input_dir = file.path(root, "input"),
  datatype = manifest$datatype,
  config = if (is.null(manifest$config)) list() else manifest$config
)

rows_con <- file(rows_path, open = "w")

emit <- function(row) {
  if (is.data.frame(row)) {
    if (nrow(row) != 1L) stop("emit() takes one row; call it once per data.frame row.")
    row <- as.list(row)
  }
  writeLines(toJSON(row, auto_unbox = TRUE, na = "null", null = "null", digits = NA), rows_con)
  invisible(NULL)
}

fail <- function(status, message) {
  close(rows_con)
  cat(message, "\n", sep = "", file = stderr())
  quit(save = "no", status = status)
}

script_env <- new.env(parent = globalenv())
assign("emit", emit, envir = script_env)

script_path <- file.path(root, "script.R")
parsed <- tryCatch(parse(script_path), error = function(e) e)
if (inherits(parsed, "error")) {
  fail(EXIT_CONTRACT_VIOLATION, paste0("script.R is not valid R: ", conditionMessage(parsed)))
}

# Just the script's own frames: those after this shim's `expr_fn()` call, minus R's own
# error-signalling frames at the end.
script_frames <- function(calls) {
  labels <- limitedLabels(calls)
  start <- match("expr_fn()", labels, nomatch = 0L) + 1L
  labels <- labels[seq.int(start, length.out = max(0L, length(labels) - start + 1L))]
  labels[!grepl("^(\\.handleSimpleError|h\\(simpleError)", labels)]
}

# The traceback is printed from a calling handler (while the failing call stack still exists),
# then the exiting handler ends the run with the script-error exit code.
run_step <- function(expr_fn) {
  tryCatch(
    withCallingHandlers(expr_fn(), error = function(e) {
      cat("Traceback (most recent call last):\n", file = stderr())
      cat(paste0("  ", script_frames(sys.calls())), sep = "\n", file = stderr())
    }),
    error = function(e) {
      call <- conditionCall(e)
      where <- if (is.null(call)) "" else paste0(" in ", deparse(call, nlines = 1L))
      fail(EXIT_SCRIPT_ERROR, paste0("Error", where, " : ", conditionMessage(e)))
    }
  )
}

run_step(function() for (expr in parsed) eval(expr, envir = script_env))

main <- get0("main", envir = script_env, inherits = FALSE)
if (!is.function(main)) {
  fail(EXIT_CONTRACT_VIOLATION, "script.R does not define a function `main`.")
}

run_step(function() main(ctx))

close(rows_con)
quit(save = "no", status = EXIT_SUCCESS)
