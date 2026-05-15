// Arduino UNO + TB6600
// 串口输入：
// F 800
// B 400

const int DIR_PIN  = 5;
const int STEP_PIN = 6;
const int EN_PIN   = 7;

const int STEP_DELAY_US = 800;

void setup() {
  pinMode(DIR_PIN, OUTPUT);
  pinMode(STEP_PIN, OUTPUT);
  pinMode(EN_PIN, OUTPUT);

  // TB6600 常见情况：LOW = 使能
  digitalWrite(EN_PIN, LOW);

  Serial.begin(9600);

  Serial.println("Stepper motor test ready.");
  Serial.println("Input command:");
  Serial.println("F 800  -> forward 800 steps");
  Serial.println("B 400  -> backward 400 steps");
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();  // 去掉空格、回车、换行

    if (command.length() == 0) {
      return;
    }

    char direction = command.charAt(0);
    int spaceIndex = command.indexOf(' ');

    if (spaceIndex == -1) {
      Serial.println("Invalid command. Use F 800 or B 400.");
      return;
    }

    int steps = command.substring(spaceIndex + 1).toInt();

    if (steps <= 0) {
      Serial.println("Invalid steps.");
      return;
    }

    if (direction == 'F' || direction == 'f') {
      Serial.print("Forward steps: ");
      Serial.println(steps);

      digitalWrite(DIR_PIN, HIGH);
      runSteps(steps);
    }
    else if (direction == 'B' || direction == 'b') {
      Serial.print("Backward steps: ");
      Serial.println(steps);

      digitalWrite(DIR_PIN, LOW);
      runSteps(steps);
    }
    else {
      Serial.println("Invalid direction. Use F or B.");
    }
  }
}

void runSteps(int steps) {
  for (int i = 0; i < steps; i++) {
    digitalWrite(STEP_PIN, HIGH);
    delayMicroseconds(STEP_DELAY_US);

    digitalWrite(STEP_PIN, LOW);
    delayMicroseconds(STEP_DELAY_US);
  }
}