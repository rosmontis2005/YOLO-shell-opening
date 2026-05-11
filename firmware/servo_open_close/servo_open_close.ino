#include <Servo.h>

Servo gateServo;

const int SERVO_PIN = 9;
const int CLOSED_ANGLE = 0;
const int OPEN_ANGLE = 90;

String incoming;

void setup() {
  Serial.begin(9600);
  gateServo.attach(SERVO_PIN);
  gateServo.write(CLOSED_ANGLE);
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

void handleCommand(String cmd) {
  cmd.trim();

  if (cmd == "1") {
    gateServo.write(OPEN_ANGLE);
    Serial.println("OK:90");
  } else if (cmd == "0") {
    gateServo.write(CLOSED_ANGLE);
    Serial.println("OK:0");
  } else {
    Serial.print("ERR:");
    Serial.println(cmd);
  }
}
