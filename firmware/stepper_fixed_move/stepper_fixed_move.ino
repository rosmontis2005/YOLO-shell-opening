const int STEP_PIN = 3;
const int DIR_PIN = 2;
const int EN_PIN = 4;

const bool DIR_RIGHT = false;
const int PULSE_US = 500;
const long MAX_STEPS_PER_COMMAND = 100000;

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

void stepMotor(long steps, bool dir) {
  digitalWrite(DIR_PIN, dir);

  for (long i = 0; i < steps; i++) {
    digitalWrite(STEP_PIN, HIGH);
    delayMicroseconds(PULSE_US);
    digitalWrite(STEP_PIN, LOW);
    delayMicroseconds(PULSE_US);
  }
}

void handleCommand(String cmd) {
  cmd.trim();

  if (!isSignedInteger(cmd)) {
    Serial.print("ERR:");
    Serial.println(cmd);
    return;
  }

  long signedSteps = cmd.toInt();
  long stepCount = signedSteps < 0 ? -signedSteps : signedSteps;
  if (stepCount > MAX_STEPS_PER_COMMAND) {
    Serial.print("ERR:RANGE:");
    Serial.println(signedSteps);
    return;
  }

  if (stepCount > 0) {
    bool dir = signedSteps > 0 ? DIR_RIGHT : !DIR_RIGHT;
    stepMotor(stepCount, dir);
  }

  Serial.print("OK:");
  Serial.println(signedSteps);
}

void setup() {
  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  pinMode(EN_PIN, OUTPUT);

  digitalWrite(EN_PIN, LOW);
  Serial.begin(9600);
  Serial.println("READY");
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
