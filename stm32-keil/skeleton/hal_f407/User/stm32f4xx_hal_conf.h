/* Auto-generated minimal HAL configuration */
#ifndef __STM32F4XX_HAL_CONF_H__
#define __STM32F4XX_HAL_CONF_H__

#ifdef __cplusplus
extern "C" {
#endif

/* Includes (CMSIS device must come first) */
#include "stm32f4xx.h"

/* Enable HAL module (required for HAL_Init, HAL_Delay, etc.) */
#define HAL_MODULE_ENABLED

/* ########################## Assert Selection ############################ */
/**
  * @brief Uncomment the line below to enable full assertion in HAL drivers.
  */
/* #define USE_FULL_ASSERT    1U */

#ifdef  USE_FULL_ASSERT
  #define assert_param(expr) ((expr) ? (void)0U : assert_failed((uint8_t *)__FILE__, __LINE__))
  void assert_failed(uint8_t* file, uint32_t line);
#else
  #define assert_param(expr) ((void)0U)
#endif /* USE_FULL_ASSERT */

#define HAL_RTC_MODULE_ENABLED
#define HAL_WWDG_MODULE_ENABLED
#define HAL_IWDG_MODULE_ENABLED
#define HAL_EXTI_MODULE_ENABLED
#define HAL_I2C_MODULE_ENABLED
#define HAL_SPI_MODULE_ENABLED
#define HAL_ADC_MODULE_ENABLED
#define HAL_TIM_MODULE_ENABLED
#define HAL_GPIO_MODULE_ENABLED
#define HAL_RCC_MODULE_ENABLED
#define HAL_CORTEX_MODULE_ENABLED
#define HAL_UART_MODULE_ENABLED
#define HAL_PWR_MODULE_ENABLED
#define HAL_FLASH_MODULE_ENABLED
#define HAL_DMA_MODULE_ENABLED

/* Exported constants (tick & timeout values) */
#define TICK_INT_PRIORITY            0x0FU
#define HSE_STARTUP_TIMEOUT          100U
#define LSE_STARTUP_TIMEOUT          5000U

/* Clock values */
#if !defined(HSE_VALUE)
#define HSE_VALUE    8000000U
#endif
#if !defined(HSI_VALUE)
#define HSI_VALUE    16000000U
#endif
#if !defined(LSE_VALUE)
#define LSE_VALUE    32768U
#endif
#if !defined(LSI_VALUE)
#define LSI_VALUE    32000U
#endif
#if !defined(EXTERNAL_CLOCK_VALUE)
#define EXTERNAL_CLOCK_VALUE 25000000U
#endif

#include "stm32f4xx_hal_gpio.h"
#include "stm32f4xx_hal_rcc.h"
#include "stm32f4xx_hal_cortex.h"
#include "stm32f4xx_hal_pwr.h"
#include "stm32f4xx_hal_flash.h"
#include "stm32f4xx_hal_dma.h"
#include "stm32f4xx_hal_uart.h"

#ifdef __cplusplus
}
#endif

#endif /* __STM32F4XX_HAL_CONF_H__ */
