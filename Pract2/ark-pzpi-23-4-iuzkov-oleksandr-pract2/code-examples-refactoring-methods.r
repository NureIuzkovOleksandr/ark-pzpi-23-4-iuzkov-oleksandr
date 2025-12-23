#Приклад 1.1
#До рефакторингу
generate_report <- function(data) {
  cat("Generating report...\n")

  sum_value <- 0
  for (x in data) {
    sum_value <- sum_value + x
  }
  cat("Total sum:", sum_value, "\n")

  avg_value <- 0
  for (x in data) {
    avg_value <- avg_value + x
  }
  avg_value <- avg_value / length(data)
  cat("Average:", avg_value, "\n")

  cat("Report generated.\n")
}
#Після рефакторингу
