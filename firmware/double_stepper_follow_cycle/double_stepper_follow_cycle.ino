#include <Servo.h>

const int M1_STEP_PIN = 3;
const int M1_DIR_PIN = 2;
const int M1_EN_PIN = 4;

const int M2_STEP_PIN = 6;
const int M2_DIR_PIN = 5;
const int M2_EN_PIN = 7;

const int SERVO_PIN = 9;
const int SERVO_MIN_DEG = 0;
const int SERVO_MAX_DEG = 180;
const int SERVO_STEP_DELAY_MS = 15;

const bool M1_DIR_RIGHT = false;
const bool M2_DIR_OUT = true;
const int PULSE_US = 500;
const long MAX_STEPS_PER_COMMAND = 100000;

Servo sweepServo;
String incoming;

bool isSignedInteger(String value) {
  value.trim();
  if (value.length() == 0) {
    return false;
  }

  int start = 0;
  if (value.charAt(0) == '+' || value.charAt(0) == '-') {
    if (value.length() == 1) {
      return false;
    }
    start = 1;
  }

  for (int i = start; i < value.length(); i++) {
    if (!isDigit(value.charAt(i))) {
      return false;
    }
  }
  return true;
}

void stepMotor(int stepPin, int dirPin, long steps, bool dir) {
  digitalWrite(dirPin, dir);

  for (long i = 0; i < steps; i++) {
    digitalWrite(stepPin, HIGH);
    delayMicroseconds(PULSE_US);
    digitalWrite(stepPin, LOW);
    delayMicroseconds(PULSE_US);
  }
}

void moveMotor1(long signedSteps) {
  long stepCount = signedSteps < 0 ? -signedSteps : signedSteps;
  if (stepCount > 0) {
    bool dir = signedSteps > 0 ? M1_DIR_RIGHT : !M1_DIR_RIGHT;
    stepMotor(M1_STEP_PIN, M1_DIR_PIN, stepCount, dir);
  }
}

void runMotor2Cycle(long oneWaySteps) {
  if (oneWaySteps <= 0) {
    return;
  }

  stepMotor(M2_STEP_PIN, M2_DIR_PIN, oneWaySteps, M2_DIR_OUT);
  stepMotor(M2_STEP_PIN, M2_DIR_PIN, oneWaySteps, !M2_DIR_OUT);
}

void runServoSweep() {
  for (int pos = SERVO_MIN_DEG; pos <= SERVO_MAX_DEG; pos += 1) {
    sweepServo.write(pos);
    delay(SERVO_STEP_DELAY_MS);
  }

  for (int pos = SERVO_MAX_DEG; pos >= SERVO_MIN_DEG; pos -= 1) {
    sweepServo.write(pos);
    delay(SERVO_STEP_DELAY_MS);
  }
}

void printErr(String message) {
  Serial.print("ERR:");
  Serial.println(message);
}

bool validateRange(long steps) {
  long stepCount = steps < 0 ? -steps : steps;
  if (stepCount > MAX_STEPS_PER_COMMAND) {
    Serial.print("ERR:RANGE:");
    Serial.println(steps);
    return false;
  }
  return true;
}

void handleMotor1Command(String value) {
  value.trim();
  if (!isSignedInteger(value)) {
    printErr(value);
    return;
  }

  long signedSteps = value.toInt();
  if (!validateRange(signedSteps)) {
    return;
  }

  moveMotor1(signedSteps);
  Serial.print("OK:M1:");
  Serial.println(signedSteps);
}

void handleMotor2CycleCommand(String value) {
  value.trim();
  if (!isSignedInteger(value)) {
    printErr(value);
    return;
  }

  long oneWaySteps = value.toInt();
  if (oneWaySteps < 0) {
    oneWaySteps = -oneWaySteps;
  }
  if (!validateRange(oneWaySteps)) {
    return;
  }

  runMotor2Cycle(oneWaySteps);
  Serial.print("OK:M2:CYCLE:");
  Serial.println(oneWaySteps);
}

void handleServoSweepCommand() {
  runServoSweep();
  Serial.println("OK:SERVO:SWEEP");
}

void handleCommand(String cmd) {
  cmd.trim();

  if (cmd.startsWith("M1:")) {
    handleMotor1Command(cmd.substring(3));
    return;
  }

  if (cmd.startsWith("M2:CYCLE:")) {
    handleMotor2CycleCommand(cmd.substring(9));
    return;
  }

  if (cmd == "SERVO:SWEEP" || cmd == "S3:SWEEP") {
    handleServoSweepCommand();
    return;
  }

  if (isSignedInteger(cmd)) {
    handleMotor1Command(cmd);
    return;
  }

  printErr(cmd);
}

void setup() {
  pinMode(M1_STEP_PIN, OUTPUT);
  pinMode(M1_DIR_PIN, OUTPUT);
  pinMode(M1_EN_PIN, OUTPUT);
  pinMode(M2_STEP_PIN, OUTPUT);
  pinMode(M2_DIR_PIN, OUTPUT);
  pinMode(M2_EN_PIN, OUTPUT);

  digitalWrite(M1_EN_PIN, LOW);
  digitalWrite(M2_EN_PIN, LOW);
  sweepServo.attach(SERVO_PIN);
  sweepServo.write(SERVO_MIN_DEG);

  Serial.begin(9600);
  Serial.println("READY:DOUBLE_STEPPING");
}

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (incoming.length() > 0) {
        handleCommand(incoming);
        incoming = "";
      }
    } else {
      incoming += c;
    }
  }
}
