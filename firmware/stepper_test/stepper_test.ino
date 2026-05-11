// 最简单步进电机测试程序
// Arduino UNO + TB6600

const int DIR_PIN  = 2;   // 方向控制
const int STEP_PIN = 3;   // 脉冲控制
const int EN_PIN   = 4;   // 使能控制

void setup() {
  pinMode(DIR_PIN, OUTPUT);
  pinMode(STEP_PIN, OUTPUT);
  pinMode(EN_PIN, OUTPUT);

  // TB6600 常见情况下：LOW = 使能
  digitalWrite(EN_PIN, LOW);
}

void loop() {
  // 正转
  digitalWrite(DIR_PIN, LOW);
  runSteps(800);

 

  // 反转
  digitalWrite(DIR_PIN, LOW);
  runSteps(800);


}

// 发送指定数量的脉冲
void runSteps(int steps) {
  for (int i = 0; i < steps; i++) {
    digitalWrite(STEP_PIN, HIGH);
    delayMicroseconds(800);

    digitalWrite(STEP_PIN, LOW);
    delayMicroseconds(800);
  }
}