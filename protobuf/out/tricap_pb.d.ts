import * as $protobuf from "protobufjs";
/** Namespace tricap. */
export namespace tricap {

    /** Properties of an IpAddress. */
    interface IIpAddress {

        /** IpAddress ip */
        ip?: (string|null);
    }

    /** Represents an IpAddress. */
    class IpAddress implements IIpAddress {

        /**
         * Constructs a new IpAddress.
         * @param [properties] Properties to set
         */
        constructor(properties?: tricap.IIpAddress);

        /** IpAddress ip. */
        public ip: string;

        /**
         * Creates a new IpAddress instance using the specified properties.
         * @param [properties] Properties to set
         * @returns IpAddress instance
         */
        public static create(properties?: tricap.IIpAddress): tricap.IpAddress;

        /**
         * Encodes the specified IpAddress message. Does not implicitly {@link tricap.IpAddress.verify|verify} messages.
         * @param message IpAddress message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: tricap.IIpAddress, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified IpAddress message, length delimited. Does not implicitly {@link tricap.IpAddress.verify|verify} messages.
         * @param message IpAddress message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: tricap.IIpAddress, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an IpAddress message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns IpAddress
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): tricap.IpAddress;

        /**
         * Decodes an IpAddress message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns IpAddress
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): tricap.IpAddress;

        /**
         * Verifies an IpAddress message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an IpAddress message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns IpAddress
         */
        public static fromObject(object: { [k: string]: any }): tricap.IpAddress;

        /**
         * Creates a plain object from an IpAddress message. Also converts values to other types if specified.
         * @param message IpAddress
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: tricap.IpAddress, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this IpAddress to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };
    }

    /** Properties of a WifiSetup. */
    interface IWifiSetup {

        /** WifiSetup ssid */
        ssid?: (string|null);

        /** WifiSetup password */
        password?: (string|null);
    }

    /** Represents a WifiSetup. */
    class WifiSetup implements IWifiSetup {

        /**
         * Constructs a new WifiSetup.
         * @param [properties] Properties to set
         */
        constructor(properties?: tricap.IWifiSetup);

        /** WifiSetup ssid. */
        public ssid: string;

        /** WifiSetup password. */
        public password: string;

        /**
         * Creates a new WifiSetup instance using the specified properties.
         * @param [properties] Properties to set
         * @returns WifiSetup instance
         */
        public static create(properties?: tricap.IWifiSetup): tricap.WifiSetup;

        /**
         * Encodes the specified WifiSetup message. Does not implicitly {@link tricap.WifiSetup.verify|verify} messages.
         * @param message WifiSetup message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: tricap.IWifiSetup, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified WifiSetup message, length delimited. Does not implicitly {@link tricap.WifiSetup.verify|verify} messages.
         * @param message WifiSetup message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: tricap.IWifiSetup, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a WifiSetup message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns WifiSetup
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): tricap.WifiSetup;

        /**
         * Decodes a WifiSetup message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns WifiSetup
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): tricap.WifiSetup;

        /**
         * Verifies a WifiSetup message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a WifiSetup message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns WifiSetup
         */
        public static fromObject(object: { [k: string]: any }): tricap.WifiSetup;

        /**
         * Creates a plain object from a WifiSetup message. Also converts values to other types if specified.
         * @param message WifiSetup
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: tricap.WifiSetup, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this WifiSetup to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };
    }

    /** Properties of a Message. */
    interface IMessage {

        /** Message msgType */
        msgType?: (tricap.Message.MessageType|null);

        /** Message ip */
        ip?: (tricap.IIpAddress|null);

        /** Message wifi */
        wifi?: (tricap.IWifiSetup|null);
    }

    /** Represents a Message. */
    class Message implements IMessage {

        /**
         * Constructs a new Message.
         * @param [properties] Properties to set
         */
        constructor(properties?: tricap.IMessage);

        /** Message msgType. */
        public msgType: tricap.Message.MessageType;

        /** Message ip. */
        public ip?: (tricap.IIpAddress|null);

        /** Message wifi. */
        public wifi?: (tricap.IWifiSetup|null);

        /**
         * Creates a new Message instance using the specified properties.
         * @param [properties] Properties to set
         * @returns Message instance
         */
        public static create(properties?: tricap.IMessage): tricap.Message;

        /**
         * Encodes the specified Message message. Does not implicitly {@link tricap.Message.verify|verify} messages.
         * @param message Message message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: tricap.IMessage, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified Message message, length delimited. Does not implicitly {@link tricap.Message.verify|verify} messages.
         * @param message Message message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: tricap.IMessage, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a Message message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns Message
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): tricap.Message;

        /**
         * Decodes a Message message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns Message
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): tricap.Message;

        /**
         * Verifies a Message message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a Message message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns Message
         */
        public static fromObject(object: { [k: string]: any }): tricap.Message;

        /**
         * Creates a plain object from a Message message. Also converts values to other types if specified.
         * @param message Message
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: tricap.Message, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this Message to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };
    }

    namespace Message {

        /** MessageType enum. */
        enum MessageType {
            IP_ADDRESS = 0,
            WIFI_SETUP = 1
        }
    }
}
