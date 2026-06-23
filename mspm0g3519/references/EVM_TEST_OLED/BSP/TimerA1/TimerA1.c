#include "TimerA1/TimerA1.h"
#include "bsp.h"

/* TimerA1 100us 周期中断
 * 注意：Timer 外设初始化由 SysConfig 生成的 SYSCFG_DL_TimerA1_init() 完成，
 * 在 SYSCFG_DL_init() 中调用。本模块仅使能 NVIC 中断。
 * 使用前需在 config.syscfg 中配置 TIMER.TimerA1 模块。 */

uint32_t nowtime = 0;
void TimerA1_INST_IRQHandler(void)
{

	switch( DL_TimerA_getPendingInterrupt(TimerA1_INST))
	{
		case DL_TIMERA_IIDX_LOAD:
			nowtime++;
		if((nowtime%5000)==0)
			LED1_toggle;
		break;
		default:
			break;
	}
}

void TimerA1_init(void)
{

	NVIC_ClearPendingIRQ(TimerA1_INST_INT_IRQN);
	NVIC_EnableIRQ(TimerA1_INST_INT_IRQN);
}



