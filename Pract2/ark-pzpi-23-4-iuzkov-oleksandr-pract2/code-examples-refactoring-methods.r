#МЕТОД EXTRACT METHOD
#До рефакторингу
analyze_sales <- function(data) {
  filtered <- data[data$price > 100, ]
  
  total <- 0
  for (i in 1:nrow(filtered)) {
    total <- total + filtered$price[i]
  }
  
  average <- total / nrow(filtered)
  
  cat("Total sales:", total, "\n")
  cat("Average price:", average, "\n")
}

#Після рефакторингу
filter_expensive_sales <- function(data) {
  data[data$price > 100, ]
}

calculate_total <- function(values) {
  sum(values)
}

calculate_average <- function(values) {
  mean(values)
}

analyze_sales <- function(data) {
  filtered <- filter_expensive_sales(data)
  
  total <- calculate_total(filtered$price)
  average <- calculate_average(filtered$price)
  
  cat("Total sales:", total, "\n")
  cat("Average price:", average, "\n")
}
#МЕТОД RENAME METHOD
#До рефакторингу
calc <- function(a, b, c) {
  if (b > c) {
    a * 0.8
  } else {
    a * 0.95
  }
}
#Після рефакторингу
calculate_discounted_price <- function(price, order_count, discount_threshold) {
  if (order_count > discount_threshold) {
    price * 0.8
  } else {
    price * 0.95
  }
}
#МЕТОД REPLACE CONDITIONAL WITH POLYMORPHISM
#До рефакторингу
calculate_tax <- function(type, income) {
  if (type == "student") {
    income * 0.05
  } else if (type == "employee") {
    income * 0.18
  } else if (type == "business") {
    income * 0.25
  } else {
    stop("Unknown taxpayer type")
  }
}
#Після рефакторингу
calculate_tax <- function(person, income) {
  UseMethod("calculate_tax")
}

calculate_tax.student <- function(person, income) {
  income * 0.05
}

calculate_tax.employee <- function(person, income) {
  income * 0.18
}

calculate_tax.business <- function(person, income) {
  income * 0.25
}
