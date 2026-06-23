/**
  * @file    main.c
  * @brief   HAL minimal template (LED blink on GPIOA pin GPIO_PIN_5)
  */
#include "stm32c0xx_hal.h"

static void SystemClock_Config(void);

int main(void)
{
    HAL_Init();
    SystemClock_Config();

    __HAL_RCC_GPIOA_CLK_ENABLE();
    GPIO_InitTypeDef g = {0};
    g.Pin = GPIO_PIN_5;
    g.Mode = GPIO_MODE_OUTPUT_PP;
    g.Pull = GPIO_NOPULL;
    g.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOA, &g);

    while (1)
    {
        HAL_GPIO_TogglePin(GPIOA, GPIO_PIN_5);
        HAL_Delay(500);
    }
}

static void SystemClock_Config(void)
{
    /* Use HSI by default (no PLL on C0). */
    RCC_OscInitTypeDef oi = {0};
    oi.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    oi.HSIState = RCC_HSI_ON;
    oi.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    HAL_RCC_OscConfig(&oi);

    RCC_ClkInitTypeDef ci = {0};
    ci.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK;
    ci.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
    ci.AHBCLKDivider = RCC_SYSCLK_DIV1;
    HAL_RCC_ClockConfig(&ci, FLASH_LATENCY_0);
}
