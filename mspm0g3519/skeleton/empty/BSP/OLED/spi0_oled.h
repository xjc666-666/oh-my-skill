#ifndef oled_spi0_h
#define oled_spi0_h

#define OLED_CMD 0  // д����
#define OLED_DATA 1 // д����
#define OLED_MODE 0

#include "bsp.h"

#define u8 unsigned char
#define u32 unsigned int

//-----------------OLED�˿ڶ���----------------
// Ҫ��SPI������Ĳ�һ��������¾���,������������

///* Port definition for Pin Group GPIO_GRP_0 */
//#define GPIO_GRP_0_PORT (GPIOB)

//#define GPIO_GRP_0_CS_PIN (DL_GPIO_PIN_6)
//#define GPIO_GRP_0_CS_IOMUX (IOMUX_PINCM23)

//#define GPIO_GRP_0_DC_PIN (DL_GPIO_PIN_7)
//#define GPIO_GRP_0_DC_IOMUX (IOMUX_PINCM24)

//#define GPIO_GRP_0_RES_PIN (DL_GPIO_PIN_1)
//#define GPIO_GRP_0_RES_IOMUX (IOMUX_PINCM13)

///* Defines for D0: GPIOB.9 with pinCMx 26 on package pin 23 */
//#define GPIO_GRP_0_D0_PIN (DL_GPIO_PIN_9)
//#define GPIO_GRP_0_D0_IOMUX (IOMUX_PINCM26)
///* Defines for D1: GPIOB.8 with pinCMx 25 on package pin 22 */
//#define GPIO_GRP_0_D1_PIN (DL_GPIO_PIN_8)
//#define GPIO_GRP_0_D1_IOMUX (IOMUX_PINCM25)

#define OLED_CS_Clr() DL_GPIO_clearPins(OLED_CS_PORT, OLED_CS_PIN)
#define OLED_CS_Set() DL_GPIO_setPins(OLED_CS_PORT, OLED_CS_PIN)

#define OLED_RST_Clr() DL_GPIO_clearPins(OLED_RES_PORT, OLED_RES_PIN)
#define OLED_RST_Set() DL_GPIO_setPins(OLED_RES_PORT, OLED_RES_PIN)

#define OLED_DC_Clr() DL_GPIO_clearPins(OLED_DC_PORT, OLED_DC_PIN)
#define OLED_DC_Set() DL_GPIO_setPins(OLED_DC_PORT, OLED_DC_PIN)

//#define OLED_SCLK_Clr() DL_GPIO_clearPins(GPIOB, GPIO_GRP_0_D0_PIN)
//#define OLED_SCLK_Set() DL_GPIO_setPins(GPIOB, GPIO_GRP_0_D0_PIN)

//#define OLED_SDIN_Clr() DL_GPIO_clearPins(GPIOB, GPIO_GRP_0_D1_PIN)
//#define OLED_SDIN_Set() DL_GPIO_setPins(GPIOB, GPIO_GRP_0_D1_PIN)
// OLEDģʽ����
// 0:4�ߴ���ģʽ
// 1:����8080ģʽ

#define SIZE 16
#define XLevelL 0x02
#define XLevelH 0x10
#define Max_Column 128
#define Max_Row 64
#define Brightness 0xFF
#define X_WIDTH 128
#define Y_WIDTH 64

// OLED�����ú���
void OLED_spi0_init(void);
// OLED�����ú���
void OLED_WR_Byte(u8 dat, u8 cmd);
void OLED_Display_On(void);
void OLED_Display_Off(void);
void OLED_Init(void);
void OLED_Clear(void);
void OLED_DrawPoint(u8 x, u8 y, u8 t);
void OLED_Fill(u8 x1, u8 y1, u8 x2, u8 y2, u8 dot);
void OLED_ShowChar(u8 x, u8 y, u8 chr);
void OLED_ShowNum(u8 x, u8 y, u32 num, u8 len, u8 size2);
void OLED_ShowString(u8 x, u8 y, u8 *p);
void OLED_Set_Pos(unsigned char x, unsigned char y);
void OLED_ShowCHinese(u8 x, u8 y, u8 no);
void OLED_DrawBMP(unsigned char x0, unsigned char y0, unsigned char x1, unsigned char y1, unsigned char BMP[]);

#endif
