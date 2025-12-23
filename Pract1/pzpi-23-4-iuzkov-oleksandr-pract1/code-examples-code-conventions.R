# Погано
x <- 10
df1 <- data.frame()

# Добре
customer_count <- 10
sales_data <- data.frame()

# Погано
data_process <- function(x) { ... }

# Добре
clean_sales_data <- function(raw_data) { ... }

# Погано
employee <- R6Class("employee", public = list(name = NULL))

# Добре
Employee <- R6Class("Employee", public = list(name = NULL))

# Погано
result <- data %>% filter(age > 18) %>% group_by(city) %>% summarise(mean_income = mean(income))

# Добре
result <- data %>%
  filter(age > 18) %>%
  group_by(city) %>%
  summarise(mean_income = mean(income))

# Погано
data <- read.csv("file.csv")

# Добре
data <- tryCatch(
  read.csv("file.csv"),
  error = function(e) {
    message("Файл не знайдено: ", e$message)
    NULL
  }
)


# Погано
employee <- list(name="Bob", salary=1000)

# Добре
Employee <- R6::R6Class("Employee",
  public = list(
    name = NULL,
    salary = NULL,
    initialize = function(name, salary) {
      self$name <- name
      self$salary <- salary
    },
    give_raise = function(amount) {
      self$salary <- self$salary + amount
    }
  )
)


library(testthat)

test_that("calculate_total додає числа правильно", {
  expect_equal(calculate_total(2,3), 5)
  expect_equal(calculate_total(0,0), 0)
})


#' Обчислює суму двох чисел
#'
#' @param x перше число
#' @param y друге число
#' @return сума x та y
calculate_total <- function(x, y) {
  x + y
}

